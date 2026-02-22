"""
Verdict engine and result data model for the stress test harness.

Kept serialisable-only and free of SerialInterface dependencies so every
function can be covered by fast, hardware-free unit tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from stress_config import ScenarioConfig

Verdict = Literal["PASS", "FAIL", "WARN"]


@dataclass
class ScenarioResult:
    """Outcome of a single stress scenario execution."""

    name: str
    run_id: str
    started_at: str  # ISO-8601
    ended_at: str  # ISO-8601
    command_profile: str
    messages_sent: int
    messages_received: int
    drop_ratio: float
    latencies_ms: list[float]
    p50_ms: float
    p95_ms: float
    p99_ms: float
    status_delta: dict[str, int]  # error counter deltas
    task_snapshot: dict[str, dict]  # task watermark / % after run
    verdict: Verdict
    failure_reasons: list[str]
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "name": self.name,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "command_profile": self.command_profile,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "drop_ratio": self.drop_ratio,
            "latencies_ms": self.latencies_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "status_delta": self.status_delta,
            "task_snapshot": self.task_snapshot,
            "verdict": self.verdict,
            "failure_reasons": self.failure_reasons,
            "tags": self.tags,
        }


@dataclass
class StressRunResult:
    """Aggregated outcome of a full stress run (all scenarios)."""

    run_id: str
    port: str
    baudrate: int
    started_at: str
    ended_at: str
    scenarios: list[ScenarioResult]
    overall_verdict: Verdict

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of the run result."""
        return {
            "run_id": self.run_id,
            "port": self.port,
            "baudrate": self.baudrate,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "overall_verdict": self.overall_verdict,
        }


# ---------------------------------------------------------------------------
# Pure verdict logic
# ---------------------------------------------------------------------------


def _percentile(values: list[float], pct: float) -> float:
    """Return the pct-th percentile of values (0-100). Returns 0.0 if empty."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * pct / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_v[lo]
    return sorted_v[lo] * (hi - k) + sorted_v[hi] * (k - lo)


def compute_latency_stats(latencies_ms: list[float]) -> tuple[float, float, float]:
    """Return (p50, p95, p99) from a list of latencies in milliseconds."""
    return (
        _percentile(latencies_ms, 50),
        _percentile(latencies_ms, 95),
        _percentile(latencies_ms, 99),
    )


def evaluate_verdict(
    cfg: ScenarioConfig,
    messages_sent: int,
    messages_received: int,
    latencies_ms: list[float],
    status_delta: dict[str, int],
) -> tuple[Verdict, list[str]]:
    """
    Pure function: compute a verdict and the list of failure reasons.

    Returns
    -------
    tuple[Verdict, list[str]]
        verdict is "PASS", "WARN", or "FAIL".
        failure_reasons is empty when verdict is "PASS".

    """
    thresholds = cfg.thresholds
    reasons: list[str] = []
    is_fail = False
    is_warn = False

    # --- Drop ratio check ---
    dropped = max(0, messages_sent - messages_received)

    if cfg.command_profile == "noise_and_recovery":
        # Noise corrupts the next valid message, causing a parsing error.
        # This inevitably drops the message, but it shouldn't fail the test
        # if the drop is accounted for by specific error counters.
        explained_drops = (
            status_delta.get("cobs_decode_error", 0)
            + status_delta.get("msg_malformed_error", 0)
            + status_delta.get("checksum_error", 0)
            + status_delta.get("receive_buffer_overflow_error", 0)
            + status_delta.get("buffer_overflow_error", 0)
        )
        unexplained_drops = max(0, dropped - explained_drops)
        drop_ratio = unexplained_drops / messages_sent if messages_sent > 0 else 0.0
    else:
        drop_ratio = dropped / messages_sent if messages_sent > 0 else 0.0
    if drop_ratio > thresholds.max_echo_drop_ratio:
        limit = thresholds.max_echo_drop_ratio
        reasons.append(f"drop_ratio={drop_ratio:.4f} exceeds limit={limit:.4f}")
        is_fail = True

    # --- Error counter deltas ---
    for key, limit in thresholds.max_error_counter_deltas.items():
        delta = status_delta.get(key, 0)
        if delta > limit:
            reasons.append(f"counter '{key}' increased by {delta} (limit={limit})")
            is_fail = True

    # --- Latency P95 check (WARN only) ---
    _, p95, _ = compute_latency_stats(latencies_ms)
    if p95 > thresholds.max_p95_latency_ms:
        limit_ms = thresholds.max_p95_latency_ms
        reasons.append(f"P95 latency={p95:.1f}ms exceeds limit={limit_ms:.1f}ms")
        is_warn = True

    if is_fail:
        return "FAIL", reasons
    if is_warn:
        return "WARN", reasons
    return "PASS", []


def aggregate_verdict(scenario_results: list[ScenarioResult]) -> Verdict:
    """Return FAIL if any scenario failed, WARN if any warned, else PASS."""
    verdicts = {r.verdict for r in scenario_results}
    if "FAIL" in verdicts:
        return "FAIL"
    if "WARN" in verdicts:
        return "WARN"
    return "PASS"
