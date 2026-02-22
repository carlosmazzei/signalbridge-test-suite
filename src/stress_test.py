"""
Stress test orchestrator.

Subclasses BaseTest to reuse publish(), handle_message(), _request_status_snapshot(),
and _calculate_status_delta(). Dispatches to scenario implementations and
produces StressRunResult via the stress_evaluator module.
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from alive_progress import alive_bar

from base_test import (
    STATISTICS_HEADER_BYTES,
    TASK_HEADER_BYTES,
    BaseTest,
)
from logger_config import setup_logging
from serial_interface import SerialCommand, SerialInterface
from stress_config import ScenarioConfig, StressConfig, default_stress_config
from stress_evaluator import (
    ScenarioResult,
    StressRunResult,
    aggregate_verdict,
    compute_latency_stats,
    evaluate_verdict,
)
from stress_reporter import print_summary, write_json_report

if TYPE_CHECKING:
    from collections.abc import Sequence

from base_test import STATISTICS_ITEMS, TASK_ITEMS

setup_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Commands available for the "mixed" profile (echo + status + task)
_MIXED_COMMANDS = [
    SerialCommand.ECHO_COMMAND,
    SerialCommand.STATISTICS_STATUS_COMMAND,
    SerialCommand.TASK_STATUS_COMMAND,
]

# Weight per command for mixed profile:  70% echo, 20% stats, 10% task
_MIXED_WEIGHTS = [0.70, 0.20, 0.10]

# Minimum inter-command gap to avoid overflowing the device at 0 pacing
_MIN_GAP_S = 0.001


class StressTest(BaseTest):
    """Orchestrate all Phase 1 stress scenarios against the firmware."""

    def __init__(
        self, ser: SerialInterface, config: StressConfig | None = None
    ) -> None:
        """Initialise with a serial interface and optional config (defaults apply)."""
        super().__init__(ser)
        self.config: StressConfig = config or default_stress_config()
        self._scenario_results: list[ScenarioResult] = []
        self._run_id: str = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Public interface (wired by ApplicationManager)
    # ------------------------------------------------------------------

    def handle_message(
        self,
        command: int,
        decoded_data: bytes,
    ) -> None:
        """Route incoming frames to BaseTest's echo/status/task handlers."""
        super().handle_message(command, decoded_data)

    def _show_options(self) -> list[ScenarioConfig]:
        """Show options to user and get input on which scenarios to run."""
        print("\nSelect Stress Scenario Profile:")
        print("0. Run ALL scenarios (default)")
        for idx, cfg in enumerate(self.config.scenarios, 1):
            print(f"{idx}. Run '{cfg.name}' only")

        choice = self._get_user_input("Enter a choice", 0)

        if choice == 0:
            return self.config.scenarios
        if 1 <= choice <= len(self.config.scenarios):
            return [self.config.scenarios[choice - 1]]

        logger.info("Invalid choice. Running ALL scenarios.")
        return self.config.scenarios

    def execute_test(self) -> StressRunResult | None:
        """Run configured scenarios interactively and return an aggregated result."""
        if self.ser is None or not self.ser.is_open():
            logger.info("No serial port found. Quitting test.")
            return None

        try:
            selected_scenarios = self._show_options()
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
            return None

        started_at = datetime.now(UTC).isoformat()
        logger.info(
            "Starting stress run %s — %d scenario(s)",
            self._run_id,
            len(selected_scenarios),
        )

        self._scenario_results = []
        for cfg in selected_scenarios:
            logger.info("=== Scenario: %s ===", cfg.name)
            result = self._run_scenario(cfg)
            self._scenario_results.append(result)
            logger.info("Scenario '%s' finished: verdict=%s", cfg.name, result.verdict)

        ended_at = datetime.now(UTC).isoformat()
        overall = aggregate_verdict(self._scenario_results)
        run_result = StressRunResult(
            run_id=self._run_id,
            port=self.ser.port,
            baudrate=self.ser.baudrate,
            started_at=started_at,
            ended_at=ended_at,
            scenarios=self._scenario_results,
            overall_verdict=overall,
        )

        report_path = write_json_report(run_result, self.config.output_dir)
        logger.info("JSON report: %s", report_path)
        print_summary(run_result)
        return run_result

    # ------------------------------------------------------------------
    # Scenario dispatcher
    # ------------------------------------------------------------------

    def _run_scenario(self, cfg: ScenarioConfig) -> ScenarioResult:
        dispatch = {
            "echo_only": self._run_echo_burst,
            "mixed": self._run_mixed_command_burst,
            "status_poll": self._run_status_poll_storm,
            "baud_flip": self._run_baud_flip,
            "noise_and_recovery": self._run_noise_and_recovery,
        }
        runner = dispatch.get(cfg.command_profile)
        if runner is None:
            logger.error("Unknown command_profile '%s'", cfg.command_profile)
            return self._make_result(
                cfg,
                started_at=datetime.now(UTC).isoformat(),
                ended_at=datetime.now(UTC).isoformat(),
                messages_sent=0,
                messages_received=0,
                latencies_ms=[],
                status_delta={},
                task_snapshot={},
            )
        return runner(cfg)

    # ------------------------------------------------------------------
    # Scenario implementations
    # ------------------------------------------------------------------

    def _run_echo_burst(self, cfg: ScenarioConfig) -> ScenarioResult:
        """Send cfg.num_messages echo commands with cfg.pacing_s gap each."""
        started_at = datetime.now(UTC).isoformat()
        self.latency_msg_sent.clear()
        self.latency_msg_received.clear()

        pre = self._request_status_snapshot()

        with alive_bar(cfg.num_messages, title=cfg.name) as pbar:
            for i in range(cfg.num_messages):
                self.publish(i, cfg.message_length)
                gap = max(cfg.pacing_s, _MIN_GAP_S)
                time.sleep(gap)
                pbar()

        # Allow outstanding responses to arrive
        time.sleep(max(cfg.pacing_s * 10, 0.5))

        post = self._request_status_snapshot()
        ended_at = datetime.now(UTC).isoformat()

        latencies_ms = [v * 1e3 for v in self.latency_msg_received.values()]
        delta = self._calculate_status_delta(pre, post)
        return self._make_result(
            cfg,
            started_at=started_at,
            ended_at=ended_at,
            messages_sent=len(self.latency_msg_sent),
            messages_received=len(self.latency_msg_received),
            latencies_ms=latencies_ms,
            status_delta=delta["statistics"],
            task_snapshot=post.get("tasks", {}),
        )

    def _run_mixed_command_burst(self, cfg: ScenarioConfig) -> ScenarioResult:
        """Randomly interleave echo, statistics, and task status requests."""
        started_at = datetime.now(UTC).isoformat()
        self.latency_msg_sent.clear()
        self.latency_msg_received.clear()

        pre = self._request_status_snapshot()
        echo_counter = 0

        with alive_bar(cfg.num_messages, title=cfg.name) as pbar:
            for i in range(cfg.num_messages):
                cmd = random.choices(_MIXED_COMMANDS, weights=_MIXED_WEIGHTS, k=1)[0]  # noqa: S311  # Randomized stress generation, not cryptography
                if cmd == SerialCommand.ECHO_COMMAND:
                    self.publish(echo_counter, cfg.message_length)
                    echo_counter += 1
                elif cmd == SerialCommand.STATISTICS_STATUS_COMMAND:
                    has_items = hasattr(self, "STATISTICS_ITEMS")
                    items_len = len(self.STATISTICS_ITEMS) if has_items else 0
                    idx = i % items_len if items_len > 0 else 0
                    self._status_update(STATISTICS_HEADER_BYTES, idx)
                else:
                    idx = i % 10
                    self._status_update(TASK_HEADER_BYTES, idx)
                gap = max(cfg.pacing_s, _MIN_GAP_S)
                time.sleep(gap)
                pbar()

        time.sleep(max(cfg.pacing_s * 10, 0.5))

        post = self._request_status_snapshot()
        ended_at = datetime.now(UTC).isoformat()
        latencies_ms = [v * 1e3 for v in self.latency_msg_received.values()]
        delta = self._calculate_status_delta(pre, post)
        return self._make_result(
            cfg,
            started_at=started_at,
            ended_at=ended_at,
            messages_sent=echo_counter,
            messages_received=len(self.latency_msg_received),
            latencies_ms=latencies_ms,
            status_delta=delta["statistics"],
            task_snapshot=post.get("tasks", {}),
        )

    def _run_status_poll_storm(self, cfg: ScenarioConfig) -> ScenarioResult:
        """Fire repeated status requests as fast as possible for duration_s."""
        started_at = datetime.now(UTC).isoformat()

        pre = self._request_status_snapshot()

        deadline = time.perf_counter() + cfg.duration_s
        requests_sent = 0
        with alive_bar(title=cfg.name) as pbar:
            while time.perf_counter() < deadline:
                for idx in STATISTICS_ITEMS:
                    self._status_update(STATISTICS_HEADER_BYTES, idx)
                    requests_sent += 1
                    if cfg.pacing_s > 0:
                        time.sleep(cfg.pacing_s)
                    pbar()
                    if time.perf_counter() >= deadline:
                        break
                for idx in TASK_ITEMS:
                    self._status_update(TASK_HEADER_BYTES, idx)
                    requests_sent += 1
                    if cfg.pacing_s > 0:
                        time.sleep(cfg.pacing_s)
                    pbar()
                    if time.perf_counter() >= deadline:
                        break

        post = self._request_status_snapshot()
        ended_at = datetime.now(UTC).isoformat()
        delta = self._calculate_status_delta(pre, post)
        # Status poll storm has no echo; set messages_sent/received to requests_sent
        return self._make_result(
            cfg,
            started_at=started_at,
            ended_at=ended_at,
            messages_sent=requests_sent,
            messages_received=requests_sent,
            latencies_ms=[],
            status_delta=delta["statistics"],
            task_snapshot=post.get("tasks", {}),
        )

    def _run_baud_flip(self, cfg: ScenarioConfig) -> ScenarioResult:
        """Cycle through baud_rates, verify echo at each, return to original."""
        started_at = datetime.now(UTC).isoformat()
        original_baud = self.ser.baudrate
        baud_rates = cfg.baud_rates or [original_baud]

        pre = self._request_status_snapshot()
        total_sent = 0
        total_received = 0
        all_latencies_ms: list[float] = []

        total_steps = len(baud_rates) * cfg.num_messages
        with alive_bar(total_steps, title=cfg.name) as pbar:
            for baud in baud_rates:
                logger.info("Switching to baud rate %d", baud)
                if not self.ser.set_baudrate(baud):
                    logger.warning("Failed to set baud rate %d, skipping", baud)
                    continue
                time.sleep(0.2)  # stabilisation

                # Re-register message handler after baud change re-creates threads
                self.ser.set_message_handler(lambda c, d, _: self.handle_message(c, d))

                self.latency_msg_sent.clear()
                self.latency_msg_received.clear()
                for i in range(cfg.num_messages):
                    self.publish(i, cfg.message_length)
                    time.sleep(max(cfg.pacing_s, 0.02))
                    pbar()
                time.sleep(0.3)

                total_sent += len(self.latency_msg_sent)
                total_received += len(self.latency_msg_received)
                all_latencies_ms.extend(
                    v * 1e3 for v in self.latency_msg_received.values()
                )

        # Restore original baud rate
        if self.ser.baudrate != original_baud:
            self.ser.set_baudrate(original_baud)
            self.ser.set_message_handler(lambda c, d, _: self.handle_message(c, d))

        post = self._request_status_snapshot()
        ended_at = datetime.now(UTC).isoformat()
        delta = self._calculate_status_delta(pre, post)
        return self._make_result(
            cfg,
            started_at=started_at,
            ended_at=ended_at,
            messages_sent=total_sent,
            messages_received=total_received,
            latencies_ms=all_latencies_ms,
            status_delta=delta["statistics"],
            task_snapshot=post.get("tasks", {}),
        )

    def _run_noise_and_recovery(self, cfg: ScenarioConfig) -> ScenarioResult:
        """Send raw garbage bytes then verify firmware recovers with a valid echo."""
        started_at = datetime.now(UTC).isoformat()

        pre = self._request_status_snapshot()

        # Inject noise directly via the underlying serial port (bypass COBS framing)
        noise_payload = bytes(random.randint(1, 255) for _ in range(cfg.noise_bytes))  # noqa: S311  # Generating random noise, not cryptography
        if self.ser.ser and self.ser.ser.is_open:
            self.ser.ser.write(noise_payload)
            self.ser.ser.flush()
            logger.info("Injected %d noise bytes", cfg.noise_bytes)

        # Wait briefly then send valid echo messages and measure recovery
        time.sleep(0.1)
        self.latency_msg_sent.clear()
        self.latency_msg_received.clear()
        recover_start = time.perf_counter()

        with alive_bar(cfg.num_messages, title=cfg.name) as pbar:
            for i in range(cfg.num_messages):
                self.publish(i, cfg.message_length)
                time.sleep(max(cfg.pacing_s, 0.02))
                pbar()

        # Wait up to max_recovery_time_s for all echos to come back
        deadline = recover_start + cfg.thresholds.max_recovery_time_s
        while time.perf_counter() < deadline:
            if len(self.latency_msg_received) >= cfg.num_messages:
                break
            time.sleep(0.01)

        post = self._request_status_snapshot()
        ended_at = datetime.now(UTC).isoformat()
        latencies_ms = [v * 1e3 for v in self.latency_msg_received.values()]
        delta = self._calculate_status_delta(pre, post)
        return self._make_result(
            cfg,
            started_at=started_at,
            ended_at=ended_at,
            messages_sent=len(self.latency_msg_sent),
            messages_received=len(self.latency_msg_received),
            latencies_ms=latencies_ms,
            status_delta=delta["statistics"],
            task_snapshot=post.get("tasks", {}),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def STATISTICS_ITEMS(self) -> Sequence[int]:  # noqa: N802  # Must match base class property name Exactly
        """Provide access to statistics items definition safely."""
        return STATISTICS_ITEMS

    def _make_result(  # noqa: PLR0913  # Result object instantiation requires many metrics
        self,
        cfg: ScenarioConfig,
        *,
        started_at: str,
        ended_at: str,
        messages_sent: int,
        messages_received: int,
        latencies_ms: list[float],
        status_delta: dict[str, int],
        task_snapshot: dict[str, Any],
    ) -> ScenarioResult:
        """Build a ScenarioResult including verdict evaluation."""
        p50, p95, p99 = compute_latency_stats(latencies_ms)
        drop_ratio = (
            (messages_sent - messages_received) / messages_sent
            if messages_sent > 0
            else 0.0
        )
        verdict, reasons = evaluate_verdict(
            cfg,
            messages_sent,
            messages_received,
            latencies_ms,
            status_delta,
        )
        return ScenarioResult(
            name=cfg.name,
            run_id=self._run_id,
            started_at=started_at,
            ended_at=ended_at,
            command_profile=cfg.command_profile,
            messages_sent=messages_sent,
            messages_received=messages_received,
            drop_ratio=drop_ratio,
            latencies_ms=latencies_ms,
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
            status_delta=status_delta,
            task_snapshot=task_snapshot,
            verdict=verdict,
            failure_reasons=reasons,
            tags=cfg.tags,
        )
