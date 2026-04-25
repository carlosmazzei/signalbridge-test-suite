"""Headless CLI runner for non-interactive test-suite execution."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from baud_rate_test import BaudRateTest
from const import BAUDRATE, PORT_NAME, TEST_RESULTS_FOLDER, TIMEOUT
from latency_test import LatencyTest
from logger_config import setup_logging
from regression_test import RegressionTest
from result_format import make_result_envelope, make_result_filename
from serial_interface import SerialInterface
from stress_config import StressConfig, default_stress_config, load_stress_config
from stress_test import StressTest

if TYPE_CHECKING:
    from collections.abc import Callable

setup_logging()
logger = logging.getLogger(__name__)

RunnerMode = str
_MODES: tuple[RunnerMode, ...] = ("latency", "baud_sweep", "stress", "regression")
_DEFAULT_BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
_RUNNER_SUMMARY_FORMAT = "runner_summary"


@dataclass(frozen=True)
class FeedbackConfig:
    """Feedback stream options."""

    enabled_stdout: bool
    jsonl_path: str
    interval_ms: int

    @property
    def enabled(self) -> bool:
        """Return whether at least one feedback sink is enabled."""
        return self.enabled_stdout or bool(self.jsonl_path.strip())


class EventSink:
    """Thread-safe JSON event sink for stdout and optional JSONL file."""

    def __init__(self, config: FeedbackConfig) -> None:
        """Initialize sink outputs based on feedback config."""
        self._config = config
        self._lock = threading.Lock()
        self._jsonl_handle = None
        if config.jsonl_path.strip():
            path = Path(config.jsonl_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._jsonl_handle = path.open("a", encoding="utf-8")

    def emit(self, event: str, **payload: Any) -> None:
        """Emit one NDJSON event record."""
        if not self._config.enabled:
            return
        record = {"event": event, "ts": time.time(), **payload}
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            if self._config.enabled_stdout:
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
            if self._jsonl_handle:
                self._jsonl_handle.write(line + "\n")
                self._jsonl_handle.flush()

    def close(self) -> None:
        """Close optional JSONL file handle."""
        if self._jsonl_handle:
            self._jsonl_handle.close()
            self._jsonl_handle = None

    @property
    def enabled(self) -> bool:
        """Return whether any event output channel is enabled."""
        return self._config.enabled


def _parse_baud_rates(raw: str | None) -> list[int] | None:
    """Parse comma-separated baud rates from CLI input."""
    if raw is None or not raw.strip():
        return None
    values = [chunk.strip() for chunk in raw.split(",")]
    return [int(value) for value in values if value]


def _parse_scenarios(raw: str | None) -> list[str] | None:
    """Parse comma-separated scenario names from CLI input."""
    if raw is None or not raw.strip():
        return None
    return [chunk.strip() for chunk in raw.split(",") if chunk.strip()]


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runner_cli",
        description=(
            "Run SignalBridge tests in headless mode for external orchestration."
        ),
    )
    parser.add_argument("--mode", required=True, choices=_MODES)
    parser.add_argument("--port", default=PORT_NAME)
    parser.add_argument("--baudrate", default=BAUDRATE, type=int)
    parser.add_argument("--timeout", default=TIMEOUT, type=float)
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path for writing a final summary JSON document.",
    )

    # Live feedback options
    parser.add_argument(
        "--feedback-stdout",
        action="store_true",
        help="Emit structured progress events as NDJSON to stdout.",
    )
    parser.add_argument(
        "--feedback-jsonl",
        default="",
        help="Optional JSONL file path for structured progress events.",
    )
    parser.add_argument(
        "--feedback-interval-ms",
        default=500,
        type=int,
        help="Heartbeat interval in milliseconds for periodic progress snapshots.",
    )

    # Shared test knobs
    parser.add_argument("--samples", default=255, type=int)
    parser.add_argument("--message-length", default=10, type=int)
    parser.add_argument("--wait-time", default=3.0, type=float)

    # Latency mode options
    parser.add_argument("--num-times", default=5, type=int)
    parser.add_argument("--max-wait", default=0.1, type=float)
    parser.add_argument("--min-wait", default=0.0, type=float)
    parser.add_argument("--jitter", action="store_true")

    # Baud sweep mode options
    parser.add_argument(
        "--baud-rates",
        default="",
        help="Comma-separated baud rates used by baud_sweep mode.",
    )

    # Stress mode options
    parser.add_argument(
        "--stress-config",
        default="",
        help="Optional JSON config file loaded via stress_config.load_stress_config.",
    )
    parser.add_argument(
        "--scenarios",
        default="",
        help="Comma-separated scenario names to run in stress mode.",
    )
    return parser


def _result_files_snapshot() -> set[Path]:
    out_dir = Path(__file__).parent.parent / TEST_RESULTS_FOLDER
    if not out_dir.exists():
        return set()
    return {p for p in out_dir.glob("*.json") if p.is_file()}


def _latest_new_file(before: set[Path], after: set[Path]) -> str | None:
    candidates = [p for p in after if p not in before]
    if not candidates:
        return None
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return str(newest.resolve())


def _load_stress_cfg(path: str) -> StressConfig:
    if path.strip():
        return load_stress_config(path)
    return default_stress_config()


def _extract_tester_counters(tester: Any) -> dict[str, Any]:
    """Return generic counters from tester objects for heartbeat events."""
    counters: dict[str, Any] = {}
    sent = getattr(tester, "latency_msg_sent", None)
    received = getattr(tester, "latency_msg_received", None)
    if isinstance(sent, dict):
        counters["latency_sent"] = len(sent)
    if isinstance(received, dict):
        counters["latency_received"] = len(received)
    scenario_results = getattr(tester, "_scenario_results", None)
    if isinstance(scenario_results, list):
        counters["scenarios_completed"] = len(scenario_results)
    return counters


def _run_feedback_loop(
    monitor: FeedbackMonitor,
) -> None:
    """Emit periodic heartbeat events while a run is active."""
    while not monitor.stop_event.wait(monitor.interval_s):
        tester = monitor.tester_getter()
        serial_stats = monitor.serial.statistics
        monitor.sink.emit(
            "heartbeat",
            mode=monitor.mode,
            elapsed_s=round(time.time() - monitor.start_time, 3),
            bytes_sent=serial_stats.bytes_sent,
            bytes_received=serial_stats.bytes_received,
            commands_sent=dict(serial_stats.commands_sent),
            commands_received=dict(serial_stats.commands_received),
            **(_extract_tester_counters(tester) if tester is not None else {}),
        )


@dataclass(frozen=True)
class FeedbackMonitor:
    """Container for heartbeat loop inputs."""

    serial: SerialInterface
    tester_getter: Callable[[], Any | None]
    sink: EventSink
    stop_event: threading.Event
    interval_s: float
    mode: str
    start_time: float


def _run_latency_mode(
    args: argparse.Namespace, serial: SerialInterface, sink: EventSink
) -> Any:
    tester = LatencyTest(serial)
    sink.emit("mode_started", mode=args.mode)
    serial.set_message_handler(lambda cmd, data, _raw: tester.handle_message(cmd, data))
    tester.execute_test_with_options(
        num_times=args.num_times,
        max_wait=args.max_wait,
        min_wait=args.min_wait,
        wait_time=args.wait_time,
        samples=args.samples,
        length=args.message_length,
        jitter=bool(args.jitter),
    )
    sink.emit("mode_finished", mode=args.mode)
    return tester


def _run_baud_mode(
    args: argparse.Namespace, serial: SerialInterface, sink: EventSink
) -> Any:
    tester = BaudRateTest(serial)
    sink.emit("mode_started", mode=args.mode)
    serial.set_message_handler(lambda cmd, data, _raw: tester.handle_message(cmd, data))
    baud_rates = _parse_baud_rates(args.baud_rates)
    tester.execute_baud_test_with_options(
        baud_rates=baud_rates or _DEFAULT_BAUD_RATES,
        samples=args.samples,
        wait_time=args.wait_time,
        length=args.message_length,
    )
    sink.emit("mode_finished", mode=args.mode)
    return tester


def _run_stress_mode(
    args: argparse.Namespace, serial: SerialInterface, sink: EventSink
) -> Any:
    cfg = _load_stress_cfg(args.stress_config)
    tester = StressTest(
        serial,
        cfg,
        progress_callback=lambda data: sink.emit(
            "stress_progress", mode=args.mode, **data
        ),
    )
    sink.emit("mode_started", mode=args.mode)
    serial.set_message_handler(lambda cmd, data, _raw: tester.handle_message(cmd, data))
    scenario_names = _parse_scenarios(args.scenarios)
    result = tester.execute_test_with_options(scenario_names=scenario_names)
    sink.emit(
        "mode_finished",
        mode=args.mode,
        overall_verdict=(result.overall_verdict if result else None),
    )
    return tester


def _run_regression_mode(
    args: argparse.Namespace, serial: SerialInterface, sink: EventSink
) -> Any:
    tester = RegressionTest(serial)
    sink.emit("mode_started", mode=args.mode)
    serial.set_message_handler(tester.handle_message)
    tester.execute_test()
    time.sleep(max(args.wait_time, 0.2))
    sink.emit("mode_finished", mode=args.mode)
    return tester


def _run_mode(args: argparse.Namespace, sink: EventSink) -> dict[str, Any]:
    serial = SerialInterface(args.port, args.baudrate, args.timeout)
    if not serial.open():
        msg = "Failed to open serial interface."
        raise RuntimeError(msg)

    before_files = _result_files_snapshot()
    started_at = time.time()
    tester_ref: dict[str, Any | None] = {"value": None}
    feedback_stop = threading.Event()
    feedback_thread: threading.Thread | None = None

    sink.emit(
        "run_started",
        mode=args.mode,
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
    )
    try:
        serial.start_reading()
        if sink.enabled and args.feedback_interval_ms > 0:
            monitor = FeedbackMonitor(
                serial=serial,
                tester_getter=lambda: tester_ref["value"],
                sink=sink,
                stop_event=feedback_stop,
                interval_s=args.feedback_interval_ms / 1000,
                mode=args.mode,
                start_time=started_at,
            )
            feedback_thread = threading.Thread(
                target=_run_feedback_loop,
                args=(monitor,),
                daemon=True,
            )
            feedback_thread.start()

        match args.mode:
            case "latency":
                tester_ref["value"] = _run_latency_mode(args, serial, sink)
            case "baud_sweep":
                tester_ref["value"] = _run_baud_mode(args, serial, sink)
            case "stress":
                tester_ref["value"] = _run_stress_mode(args, serial, sink)
            case "regression":
                tester_ref["value"] = _run_regression_mode(args, serial, sink)
            case _:
                msg = f"Unsupported mode '{args.mode}'."
                raise ValueError(msg)
    finally:
        feedback_stop.set()
        if feedback_thread and feedback_thread.is_alive():
            feedback_thread.join(timeout=1.0)
        serial.close()

    after_files = _result_files_snapshot()
    result_file = _latest_new_file(before_files, after_files)
    finished_at = time.time()
    summary = {
        "mode": args.mode,
        "port": args.port,
        "baudrate": args.baudrate,
        "timeout": args.timeout,
        "duration_s": round(finished_at - started_at, 3),
        "result_file": result_file,
    }
    sink.emit("run_finished", summary=summary)
    return summary


def _write_summary(path: str, summary: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _write_runner_summary_file(summary: dict[str, Any]) -> str:
    """Persist runner summary to test_results using project naming conventions."""
    run_id = uuid.uuid4().hex[:8]
    file_name = make_result_filename("runner", run_id)
    target = Path(__file__).parent.parent / TEST_RESULTS_FOLDER / file_name
    target.parent.mkdir(parents=True, exist_ok=True)
    envelope = make_result_envelope(_RUNNER_SUMMARY_FORMAT, summary)
    target.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(target.resolve())


def main() -> int:
    """Run selected mode and emit summary and optional progress feedback."""
    parser = _make_parser()
    args = parser.parse_args()
    feedback_cfg = FeedbackConfig(
        enabled_stdout=bool(args.feedback_stdout),
        jsonl_path=args.feedback_jsonl,
        interval_ms=max(args.feedback_interval_ms, 0),
    )
    sink = EventSink(feedback_cfg)
    try:
        summary = _run_mode(args, sink)
        summary["summary_file"] = _write_runner_summary_file(summary)
        if args.output_json:
            _write_summary(args.output_json, summary)
        # Preserve old behavior when stdout feedback is disabled.
        if not feedback_cfg.enabled_stdout:
            sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Headless runner failed")
        sink.emit("run_failed")
        return 1
    finally:
        sink.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
