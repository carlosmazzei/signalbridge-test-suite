"""
Unit tests for stress_evaluator: verdict logic, percentile computation, aggregation.

All tests are hardware-free — no SerialInterface dependency.
"""

from __future__ import annotations

import pytest

from stress_config import ScenarioConfig, ScenarioThresholds
from stress_evaluator import (
    ScenarioResult,
    StressRunResult,
    aggregate_verdict,
    compute_latency_stats,
    evaluate_verdict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(
    *,
    max_drop: float = 0.001,
    max_p95: float = 50.0,
    counter_limits: dict | None = None,
    recovery_s: float = 2.0,
) -> ScenarioConfig:
    return ScenarioConfig(
        name="test_scenario",
        duration_s=10.0,
        command_profile="echo_only",
        thresholds=ScenarioThresholds(
            max_echo_drop_ratio=max_drop,
            max_error_counter_deltas=counter_limits or {},
            max_p95_latency_ms=max_p95,
            max_recovery_time_s=recovery_s,
        ),
    )


def _result(verdict: str, reasons: list[str] | None = None) -> ScenarioResult:
    return ScenarioResult(
        name="x",
        run_id="r",
        started_at="",
        ended_at="",
        command_profile="echo_only",
        messages_sent=100,
        messages_received=100,
        drop_ratio=0.0,
        latencies_ms=[],
        p50_ms=0.0,
        p95_ms=0.0,
        p99_ms=0.0,
        status_delta={},
        task_snapshot={},
        verdict=verdict,  # type: ignore[arg-type]
        failure_reasons=reasons or [],
    )


# ---------------------------------------------------------------------------
# compute_latency_stats
# ---------------------------------------------------------------------------


class TestComputeLatencyStats:
    def test_empty_list_returns_zeros(self) -> None:
        assert compute_latency_stats([]) == (0.0, 0.0, 0.0)

    def test_single_value(self) -> None:
        p50, p95, p99 = compute_latency_stats([10.0])
        assert p50 == pytest.approx(10.0)
        assert p95 == pytest.approx(10.0)

    def test_known_values(self) -> None:
        values = list(range(1, 101))  # 1..100
        p50, p95, p99 = compute_latency_stats([float(v) for v in values])
        assert p50 == pytest.approx(50.5, abs=1.0)
        assert p95 == pytest.approx(95.05, abs=1.0)
        assert p99 == pytest.approx(99.01, abs=1.0)


# ---------------------------------------------------------------------------
# evaluate_verdict — PASS cases
# ---------------------------------------------------------------------------


class TestPassConditions:
    def test_all_clear_returns_pass(self) -> None:
        verdict, reasons = evaluate_verdict(_cfg(), 100, 100, [10.0, 15.0, 20.0], {})
        assert verdict == "PASS"
        assert reasons == []

    def test_zero_messages_sent_no_crash(self) -> None:
        verdict, _ = evaluate_verdict(_cfg(), 0, 0, [], {})
        assert verdict == "PASS"

    def test_empty_latency_list_ok_when_below_threshold(self) -> None:
        # No latencies → P95 = 0 < 50 threshold → PASS
        verdict, _ = evaluate_verdict(_cfg(max_p95=50.0), 10, 10, [], {})
        assert verdict == "PASS"


# ---------------------------------------------------------------------------
# evaluate_verdict — FAIL cases
# ---------------------------------------------------------------------------


class TestDropRatioFail:
    def test_drop_above_limit_is_fail(self) -> None:
        verdict, reasons = evaluate_verdict(_cfg(max_drop=0.001), 1000, 990, [], {})
        assert verdict == "FAIL"
        assert any("drop_ratio" in r for r in reasons)

    def test_drop_exactly_at_limit_passes(self) -> None:
        # 1 drop out of 1000 = 0.001 exactly → should PASS (not strictly greater)
        verdict, _ = evaluate_verdict(_cfg(max_drop=0.001), 1000, 999, [], {})
        assert verdict == "PASS"

    def test_all_dropped_is_fail(self) -> None:
        verdict, _ = evaluate_verdict(_cfg(max_drop=0.001), 100, 0, [], {})
        assert verdict == "FAIL"


class TestNoiseAndRecoveryDrops:
    def test_unexplained_drops_fail(self) -> None:
        cfg = _cfg(max_drop=0.0)
        cfg.command_profile = "noise_and_recovery"
        verdict, reasons = evaluate_verdict(cfg, 10, 8, [], {"msg_malformed_error": 1})
        assert verdict == "FAIL"
        assert any("drop_ratio" in r for r in reasons)

    def test_explained_drops_pass(self) -> None:
        cfg = _cfg(max_drop=0.0)
        cfg.command_profile = "noise_and_recovery"
        verdict, _ = evaluate_verdict(
            cfg,
            10,
            8,
            [],
            {"msg_malformed_error": 1, "receive_buffer_overflow_error": 1},
        )
        assert verdict == "PASS"

    def test_normal_profile_ignores_error_counters_for_drops(self) -> None:
        cfg = _cfg(max_drop=0.0)
        cfg.command_profile = "echo_only"
        verdict, reasons = evaluate_verdict(cfg, 10, 8, [], {"msg_malformed_error": 2})
        assert verdict == "FAIL"
        assert any("drop_ratio" in r for r in reasons)


class TestErrorCounterFail:
    def test_single_counter_exceeds_budget(self) -> None:
        verdict, reasons = evaluate_verdict(
            _cfg(counter_limits={"buffer_overflow_error": 0}),
            100,
            100,
            [],
            {"buffer_overflow_error": 1},
        )
        assert verdict == "FAIL"
        assert any("buffer_overflow_error" in r for r in reasons)

    def test_counter_at_limit_passes(self) -> None:
        verdict, _ = evaluate_verdict(
            _cfg(counter_limits={"buffer_overflow_error": 2}),
            100,
            100,
            [],
            {"buffer_overflow_error": 2},
        )
        assert verdict == "PASS"

    def test_unconstrained_counter_ignored(self) -> None:
        # "checksum_error" not in counter_limits → no limit → PASS
        verdict, _ = evaluate_verdict(
            _cfg(counter_limits={}), 100, 100, [], {"checksum_error": 999}
        )
        assert verdict == "PASS"


class TestMultipleViolations:
    def test_drop_and_counter_both_fail(self) -> None:
        verdict, reasons = evaluate_verdict(
            _cfg(max_drop=0.001, counter_limits={"buffer_overflow_error": 0}),
            100,
            90,
            [],
            {"buffer_overflow_error": 5},
        )
        assert verdict == "FAIL"
        assert len(reasons) == 2

    def test_fail_overrides_warn(self) -> None:
        # Both drop (FAIL) and high P95 (WARN) → FAIL wins
        verdict, _ = evaluate_verdict(
            _cfg(max_drop=0.001, max_p95=5.0), 100, 90, [100.0, 200.0], {}
        )
        assert verdict == "FAIL"


# ---------------------------------------------------------------------------
# evaluate_verdict — WARN cases
# ---------------------------------------------------------------------------


class TestLatencyWarn:
    def test_p95_over_threshold_is_warn(self) -> None:
        latencies = [50.0] * 95 + [200.0] * 5  # P95 ≈ 200ms
        verdict, reasons = evaluate_verdict(_cfg(max_p95=50.0), 100, 100, latencies, {})
        assert verdict == "WARN"
        assert any("P95" in r for r in reasons)

    def test_p95_just_below_threshold_passes(self) -> None:
        latencies = [10.0] * 100
        verdict, _ = evaluate_verdict(_cfg(max_p95=50.0), 100, 100, latencies, {})
        assert verdict == "PASS"


# ---------------------------------------------------------------------------
# aggregate_verdict
# ---------------------------------------------------------------------------


class TestAggregateVerdict:
    def test_all_pass_gives_pass(self) -> None:
        assert aggregate_verdict([_result("PASS"), _result("PASS")]) == "PASS"

    def test_one_fail_gives_fail(self) -> None:
        assert aggregate_verdict([_result("PASS"), _result("FAIL")]) == "FAIL"

    def test_one_warn_gives_warn(self) -> None:
        assert aggregate_verdict([_result("PASS"), _result("WARN")]) == "WARN"

    def test_fail_beats_warn(self) -> None:
        assert aggregate_verdict([_result("WARN"), _result("FAIL")]) == "FAIL"

    def test_empty_list_gives_pass(self) -> None:
        assert aggregate_verdict([]) == "PASS"


# ---------------------------------------------------------------------------
# ScenarioResult.to_dict / StressRunResult.to_dict
# ---------------------------------------------------------------------------


class TestResultSerialization:
    def test_scenario_result_to_dict_has_required_keys(self) -> None:
        r = _result("PASS")
        d = r.to_dict()
        for key in (
            "name",
            "verdict",
            "drop_ratio",
            "p95_ms",
            "status_delta",
            "latencies_ms",
        ):
            assert key in d

    def test_stress_run_result_to_dict_has_required_keys(self) -> None:
        run = StressRunResult(
            run_id="r1",
            port="/dev/ttyACM0",
            baudrate=230400,
            started_at="",
            ended_at="",
            scenarios=[_result("PASS")],
            overall_verdict="PASS",
        )
        d = run.to_dict()
        for key in ("run_id", "port", "baudrate", "overall_verdict", "scenarios"):
            assert key in d
