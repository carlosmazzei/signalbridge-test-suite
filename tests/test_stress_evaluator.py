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
    _percentile,
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

    def test_scenario_result_to_dict_values(self) -> None:
        r = ScenarioResult(
            name="val_scenario",
            run_id="run_42",
            started_at="2024-01-01T00:00:00Z",
            ended_at="2024-01-01T00:01:00Z",
            command_profile="echo_only",
            messages_sent=200,
            messages_received=195,
            drop_ratio=0.025,
            latencies_ms=[5.0, 10.0],
            p50_ms=7.5,
            p95_ms=9.75,
            p99_ms=9.95,
            status_delta={"checksum_error": 3},
            task_snapshot={"task1": {"pct": 80}},
            verdict="FAIL",
            failure_reasons=["too many drops"],
            tags=["nightly"],
        )
        d = r.to_dict()
        assert d["name"] == "val_scenario"
        assert d["run_id"] == "run_42"
        assert d["started_at"] == "2024-01-01T00:00:00Z"
        assert d["ended_at"] == "2024-01-01T00:01:00Z"
        assert d["command_profile"] == "echo_only"
        assert d["messages_sent"] == 200
        assert d["messages_received"] == 195
        assert d["drop_ratio"] == pytest.approx(0.025)
        assert d["latencies_ms"] == [5.0, 10.0]
        assert d["p50_ms"] == pytest.approx(7.5)
        assert d["p95_ms"] == pytest.approx(9.75)
        assert d["p99_ms"] == pytest.approx(9.95)
        assert d["status_delta"] == {"checksum_error": 3}
        assert d["task_snapshot"] == {"task1": {"pct": 80}}
        assert d["verdict"] == "FAIL"
        assert d["failure_reasons"] == ["too many drops"]
        assert d["tags"] == ["nightly"]

    def test_stress_run_result_to_dict_values(self) -> None:
        scenario = _result("WARN", ["high latency"])
        run = StressRunResult(
            run_id="run_99",
            port="/dev/ttyUSB0",
            baudrate=115200,
            started_at="2024-06-01T12:00:00Z",
            ended_at="2024-06-01T12:05:00Z",
            scenarios=[scenario],
            overall_verdict="WARN",
        )
        d = run.to_dict()
        assert d["run_id"] == "run_99"
        assert d["port"] == "/dev/ttyUSB0"
        assert d["baudrate"] == 115200
        assert d["started_at"] == "2024-06-01T12:00:00Z"
        assert d["ended_at"] == "2024-06-01T12:05:00Z"
        assert d["overall_verdict"] == "WARN"
        assert len(d["scenarios"]) == 1
        assert d["scenarios"][0]["verdict"] == "WARN"
        assert d["scenarios"][0]["failure_reasons"] == ["high latency"]


# ---------------------------------------------------------------------------
# _percentile — tight tolerance & interpolation
# ---------------------------------------------------------------------------


class TestPercentilePrecision:
    def test_percentile_interpolation_precision(self) -> None:
        """Test _percentile directly with known values and tight tolerance."""
        values = [float(v) for v in range(1, 101)]  # 1.0 .. 100.0
        # For 100 elements: k = 99 * pct / 100
        # p50: k = 49.5  → 50*0.5 + 51*0.5 = 50.5
        assert _percentile(values, 50) == pytest.approx(50.5, abs=0.01)
        # p95: k = 94.05 → 95*0.95 + 96*0.05 = 90.25 + 4.8 = 95.05
        assert _percentile(values, 95) == pytest.approx(95.05, abs=0.01)
        # p99: k = 98.01 → 99*0.99 + 100*0.01 = 98.01 + 1.0 = 99.01
        assert _percentile(values, 99) == pytest.approx(99.01, abs=0.01)

    def test_two_element_list(self) -> None:
        """Exercise the interpolation formula where floor != ceil."""
        values = [10.0, 20.0]
        # p50: k = (2-1)*50/100 = 0.5  → lo=0, hi=1
        #   10.0 * (1 - 0.5) + 20.0 * (0.5 - 0) = 5.0 + 10.0 = 15.0
        assert _percentile(values, 50) == pytest.approx(15.0, abs=0.01)
        # p95: k = 1*95/100 = 0.95 → lo=0, hi=1
        #   10.0 * (1 - 0.95) + 20.0 * (0.95 - 0) = 0.5 + 19.0 = 19.5
        assert _percentile(values, 95) == pytest.approx(19.5, abs=0.01)
        # p99: k = 1*99/100 = 0.99 → lo=0, hi=1
        #   10.0 * (1 - 0.99) + 20.0 * (0.99 - 0) = 0.1 + 19.8 = 19.9
        assert _percentile(values, 99) == pytest.approx(19.9, abs=0.01)


# ---------------------------------------------------------------------------
# compute_latency_stats — p99 known value
# ---------------------------------------------------------------------------


class TestComputeLatencyStatsP99:
    def test_known_values_p99(self) -> None:
        values = [float(v) for v in range(1, 101)]  # 1.0 .. 100.0
        _, _, p99 = compute_latency_stats(values)
        assert p99 == pytest.approx(99.01, abs=0.01)


# ---------------------------------------------------------------------------
# evaluate_verdict — drop fail reason content
# ---------------------------------------------------------------------------


class TestDropFailReasonContent:
    def test_drop_fail_reason_contains_ratio(self) -> None:
        """Check the reason field contains the actual drop ratio value."""
        verdict, reasons = evaluate_verdict(_cfg(max_drop=0.001), 1000, 900, [], {})
        assert verdict == "FAIL"
        assert len(reasons) >= 1
        # drop_ratio = 100/1000 = 0.1000
        drop_reason = next(r for r in reasons if "drop_ratio" in r)
        assert "0.1000" in drop_reason


# ---------------------------------------------------------------------------
# evaluate_verdict — expected_counter_deltas (fault_injection profile)
# ---------------------------------------------------------------------------


def _fi_cfg(
    *,
    expected: dict[str, int],
    max_limits: dict[str, int] | None = None,
) -> ScenarioConfig:
    """Build a fault_injection ScenarioConfig for evaluator tests."""
    return ScenarioConfig(
        name="fi_test",
        duration_s=5.0,
        command_profile="fault_injection",
        thresholds=ScenarioThresholds(
            max_echo_drop_ratio=1.0,
            max_error_counter_deltas=max_limits or {},
            expected_counter_deltas=expected,
        ),
    )


class TestExpectedCounterDeltas:
    def test_exact_match_passes(self) -> None:
        verdict, reasons = evaluate_verdict(
            _fi_cfg(expected={"cobs_decode_error": 1}),
            0,
            0,
            [],
            {"cobs_decode_error": 1},
        )
        assert verdict == "PASS"
        assert reasons == []

    def test_delta_too_high_fails(self) -> None:
        verdict, _ = evaluate_verdict(
            _fi_cfg(expected={"cobs_decode_error": 1}),
            0,
            0,
            [],
            {"cobs_decode_error": 2},
        )
        assert verdict == "FAIL"

    def test_delta_too_low_fails(self) -> None:
        verdict, reasons = evaluate_verdict(
            _fi_cfg(expected={"cobs_decode_error": 1}),
            0,
            0,
            [],
            {"cobs_decode_error": 0},
        )
        assert verdict == "FAIL"
        assert any("cobs_decode_error" in r for r in reasons)

    def test_missing_counter_defaults_to_zero(self) -> None:
        # key absent in status_delta → treated as 0; expected=1 → FAIL
        verdict, _ = evaluate_verdict(
            _fi_cfg(expected={"cobs_decode_error": 1}),
            0,
            0,
            [],
            {},
        )
        assert verdict == "FAIL"

    def test_multiple_counters_all_must_match(self) -> None:
        # Both expected; one wrong → FAIL
        verdict, reasons = evaluate_verdict(
            _fi_cfg(
                expected={
                    "receive_buffer_overflow_error": 2,
                    "cobs_decode_error": 1,
                }
            ),
            0,
            0,
            [],
            {"receive_buffer_overflow_error": 2, "cobs_decode_error": 0},
        )
        assert verdict == "FAIL"
        assert any("cobs_decode_error" in r for r in reasons)

    def test_expected_independent_of_max(self) -> None:
        # max check passes (3 ≤ 5), exact check fails (3 ≠ 1) → FAIL
        verdict, reasons = evaluate_verdict(
            _fi_cfg(
                expected={"cobs_decode_error": 1},
                max_limits={"cobs_decode_error": 5},
            ),
            0,
            0,
            [],
            {"cobs_decode_error": 3},
        )
        assert verdict == "FAIL"
        assert any("expected exactly 1" in r for r in reasons)

    def test_fault_injection_zero_messages_no_drop_fail(self) -> None:
        # messages_sent=0, messages_received=0, drop_ratio guard → no FAIL
        verdict, _ = evaluate_verdict(
            _fi_cfg(expected={"cobs_decode_error": 1}),
            0,
            0,
            [],
            {"cobs_decode_error": 1},
        )
        assert verdict == "PASS"

    def test_reason_contains_counter_name_and_values(self) -> None:
        _, reasons = evaluate_verdict(
            _fi_cfg(expected={"checksum_error": 1}),
            0,
            0,
            [],
            {"checksum_error": 2},
        )
        assert len(reasons) == 1
        assert "checksum_error" in reasons[0]
        assert "delta=2" in reasons[0]
        assert "expected exactly 1" in reasons[0]
