"""Typed configuration schema and loader for the stress test harness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from const import TEST_RESULTS_FOLDER

DEFAULT_CONFIG_FILENAME = "stress_config.json"


@dataclass
class ScenarioThresholds:
    """Pass/fail thresholds for a single scenario."""

    # Echo drop ratio — 0.001 = 99.9% success required
    max_echo_drop_ratio: float = 0.001
    # Maximum allowed increase in each error counter during the scenario.
    # Keys are STATISTICS_ITEMS names.  Missing keys mean "no limit".
    max_error_counter_deltas: dict[str, int] = field(default_factory=dict)
    # P95 round-trip latency in milliseconds — exceeded → WARN
    max_p95_latency_ms: float = 50.0
    # Maximum acceptable recovery time after a noise burst (seconds)
    max_recovery_time_s: float = 2.0


@dataclass
class ScenarioConfig:
    """Definition of a single stress scenario."""

    name: str
    duration_s: float
    # "echo_only" | "mixed" | "status_poll" | "baud_flip" | "noise_and_recovery"
    command_profile: str
    pacing_s: float = 0.0  # inter-message gap; 0 = max rate
    message_length: int = 10  # COBS payload length (6-10 bytes)
    num_messages: int = 500
    baud_rates: list[int] = field(default_factory=list)  # used by baud_flip
    noise_bytes: int = 64  # used by noise_and_recovery
    thresholds: ScenarioThresholds = field(default_factory=ScenarioThresholds)
    tags: list[str] = field(default_factory=list)


@dataclass
class StressConfig:
    """Top-level configuration for a stress test run."""

    scenarios: list[ScenarioConfig]
    output_dir: str = TEST_RESULTS_FOLDER


# ---------------------------------------------------------------------------
# Default configuration factory
# ---------------------------------------------------------------------------


def default_stress_config() -> StressConfig:
    """Return a ready-to-run StressConfig with all five Phase 1 scenarios."""
    return StressConfig(
        output_dir=TEST_RESULTS_FOLDER,
        scenarios=[
            ScenarioConfig(
                name="echo_burst",
                duration_s=30.0,
                command_profile="echo_only",
                pacing_s=0.005,
                message_length=10,
                num_messages=500,
                thresholds=ScenarioThresholds(
                    max_echo_drop_ratio=0.001,
                    max_error_counter_deltas={"buffer_overflow_error": 0},
                    max_p95_latency_ms=50.0,
                ),
                tags=["ci", "quick"],
            ),
            ScenarioConfig(
                name="mixed_command_burst",
                duration_s=45.0,
                command_profile="mixed",
                pacing_s=0.01,
                message_length=10,
                num_messages=400,
                thresholds=ScenarioThresholds(
                    max_echo_drop_ratio=0.005,
                    max_p95_latency_ms=100.0,
                ),
                tags=["ci"],
            ),
            ScenarioConfig(
                name="status_poll_storm",
                duration_s=20.0,
                command_profile="status_poll",
                pacing_s=0.0,
                num_messages=200,
                thresholds=ScenarioThresholds(
                    max_echo_drop_ratio=1.0,  # no echo expected
                    max_error_counter_deltas={"queue_send_error": 0},
                    max_p95_latency_ms=200.0,
                ),
                tags=["ci"],
            ),
            ScenarioConfig(
                name="baud_flip",
                duration_s=60.0,
                command_profile="baud_flip",
                pacing_s=0.0,
                num_messages=5,  # echo verifications per baud rate
                baud_rates=[9600, 57600, 115200, 230400],
                thresholds=ScenarioThresholds(
                    max_echo_drop_ratio=0.0,
                    max_p95_latency_ms=200.0,
                    max_recovery_time_s=3.0,
                ),
                tags=["hil"],
            ),
            ScenarioConfig(
                name="noise_and_recovery",
                duration_s=15.0,
                command_profile="noise_and_recovery",
                noise_bytes=64,
                num_messages=10,  # echo verifications after noise
                thresholds=ScenarioThresholds(
                    max_echo_drop_ratio=0.0,  # must recover fully
                    max_p95_latency_ms=2000.0,
                    max_recovery_time_s=2.0,
                ),
                tags=["ci", "fault_injection"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def _scenario_thresholds_from_dict(d: dict[str, Any]) -> ScenarioThresholds:
    return ScenarioThresholds(
        max_echo_drop_ratio=d.get("max_echo_drop_ratio", 0.001),
        max_error_counter_deltas=d.get("max_error_counter_deltas", {}),
        max_p95_latency_ms=d.get("max_p95_latency_ms", 50.0),
        max_recovery_time_s=d.get("max_recovery_time_s", 2.0),
    )


def _scenario_from_dict(d: dict[str, Any]) -> ScenarioConfig:
    return ScenarioConfig(
        name=d["name"],
        duration_s=float(d.get("duration_s", 30.0)),
        command_profile=d.get("command_profile", "echo_only"),
        pacing_s=float(d.get("pacing_s", 0.0)),
        message_length=int(d.get("message_length", 10)),
        num_messages=int(d.get("num_messages", 500)),
        baud_rates=d.get("baud_rates", []),
        noise_bytes=int(d.get("noise_bytes", 64)),
        thresholds=_scenario_thresholds_from_dict(d.get("thresholds", {})),
        tags=d.get("tags", []),
    )


def load_stress_config(path: str | Path) -> StressConfig:
    """Load a StressConfig from a JSON file."""
    with Path(path).open(encoding="utf-8") as f:
        data = json.load(f)
    return StressConfig(
        output_dir=data.get("output_dir", "results"),
        scenarios=[_scenario_from_dict(s) for s in data.get("scenarios", [])],
    )
