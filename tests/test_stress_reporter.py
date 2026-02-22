"""Tests for stress_reporter: JSON file output and console summary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stress_evaluator import ScenarioResult, StressRunResult
from stress_reporter import print_summary, write_json_report

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scenario_result(verdict: str = "PASS") -> ScenarioResult:
    return ScenarioResult(
        name="echo_burst",
        run_id="run-1",
        started_at="2026-01-01T00:00:00+00:00",
        ended_at="2026-01-01T00:00:30+00:00",
        command_profile="echo_only",
        messages_sent=500,
        messages_received=499,
        drop_ratio=0.002,
        latencies_ms=[10.0, 15.0, 20.0],
        p50_ms=15.0,
        p95_ms=19.5,
        p99_ms=19.9,
        status_delta={"checksum_error": 0, "buffer_overflow_error": 0},
        task_snapshot={"cdc_task": {"percent_time": 5, "high_watermark": 100}},
        verdict=verdict,  # type: ignore[arg-type]
        failure_reasons=[]
        if verdict == "PASS"
        else ["drop_ratio=0.002 exceeds limit=0.001"],
        tags=["ci"],
    )


def _run_result(verdict: str = "PASS") -> StressRunResult:
    return StressRunResult(
        run_id="run-1",
        port="/dev/ttyACM0",
        baudrate=230400,
        started_at="2026-01-01T00:00:00+00:00",
        ended_at="2026-01-01T00:02:00+00:00",
        scenarios=[_scenario_result(verdict)],
        overall_verdict=verdict,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# write_json_report
# ---------------------------------------------------------------------------


class TestWriteJsonReport:
    def test_file_created(self, tmp_path: Path) -> None:
        result = _run_result()
        out_path = write_json_report(result, output_dir=str(tmp_path))
        assert out_path.exists()

    def test_file_contains_valid_json(self, tmp_path: Path) -> None:
        result = _run_result()
        out_path = write_json_report(result, output_dir=str(tmp_path))
        with out_path.open(encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_json_has_required_top_level_keys(self, tmp_path: Path) -> None:
        result = _run_result()
        out_path = write_json_report(result, output_dir=str(tmp_path))
        with out_path.open(encoding="utf-8") as f:
            data = json.load(f)
        for key in (
            "run_id",
            "port",
            "baudrate",
            "overall_verdict",
            "scenarios",
            "started_at",
            "ended_at",
        ):
            assert key in data, f"Missing key: {key}"

    def test_scenario_has_required_keys(self, tmp_path: Path) -> None:
        result = _run_result()
        out_path = write_json_report(result, output_dir=str(tmp_path))
        with out_path.open(encoding="utf-8") as f:
            data = json.load(f)
        scenario = data["scenarios"][0]
        for key in (
            "name",
            "verdict",
            "drop_ratio",
            "p95_ms",
            "status_delta",
            "latencies_ms",
            "failure_reasons",
        ):
            assert key in scenario, f"Missing scenario key: {key}"

    def test_output_dir_created_if_missing(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        result = _run_result()
        write_json_report(result, output_dir=str(nested))
        assert nested.exists()

    def test_filename_contains_run_id(self, tmp_path: Path) -> None:
        result = _run_result()
        out_path = write_json_report(result, output_dir=str(tmp_path))
        assert result.run_id in out_path.name

    def test_overall_verdict_preserved(self, tmp_path: Path) -> None:
        result = _run_result("FAIL")
        out_path = write_json_report(result, output_dir=str(tmp_path))
        with out_path.open(encoding="utf-8") as f:
            data = json.load(f)
        assert data["overall_verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# print_summary
# ---------------------------------------------------------------------------


class TestPrintSummary:
    def test_does_not_raise(self, capsys: pytest.CaptureFixture) -> None:
        print_summary(_run_result("PASS"))

    def test_verdict_appears_in_output(self, capsys: pytest.CaptureFixture) -> None:
        print_summary(_run_result("PASS"))
        out = capsys.readouterr().out
        assert "PASS" in out

    def test_fail_verdict_appears(self, capsys: pytest.CaptureFixture) -> None:
        print_summary(_run_result("FAIL"))
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_scenario_name_appears(self, capsys: pytest.CaptureFixture) -> None:
        print_summary(_run_result())
        out = capsys.readouterr().out
        assert "echo_burst" in out

    def test_failure_reason_appears_for_fail(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        print_summary(_run_result("FAIL"))
        out = capsys.readouterr().out
        assert "drop_ratio" in out

    def test_run_id_appears(self, capsys: pytest.CaptureFixture) -> None:
        print_summary(_run_result())
        out = capsys.readouterr().out
        assert "run-1" in out

    def test_multiple_scenarios_all_appear(self, capsys: pytest.CaptureFixture) -> None:
        run = StressRunResult(
            run_id="run-multi",
            port="/dev/ttyACM0",
            baudrate=230400,
            started_at="",
            ended_at="",
            scenarios=[
                _scenario_result("PASS"),
                ScenarioResult(
                    name="mixed_command_burst",
                    run_id="run-multi",
                    started_at="",
                    ended_at="",
                    command_profile="mixed",
                    messages_sent=200,
                    messages_received=200,
                    drop_ratio=0.0,
                    latencies_ms=[],
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    status_delta={},
                    task_snapshot={},
                    verdict="WARN",
                    failure_reasons=["P95 latency=110.0ms exceeds limit=100.0ms"],
                ),
            ],
            overall_verdict="WARN",
        )
        print_summary(run)
        out = capsys.readouterr().out
        assert "echo_burst" in out
        assert "mixed_command_burst" in out
        assert "WARN" in out
