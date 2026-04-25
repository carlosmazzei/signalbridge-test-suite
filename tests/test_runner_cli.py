"""Tests for headless CLI helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from runner_cli import (
    EventSink,
    FeedbackConfig,
    _extract_tester_counters,
    _latest_new_file,
    _parse_baud_rates,
    _parse_scenarios,
    _write_runner_summary_file,
)


def test_parse_baud_rates_with_values() -> None:
    """Parses comma-separated baud rates into integers."""
    assert _parse_baud_rates("9600, 115200,230400") == [9600, 115200, 230400]


def test_parse_baud_rates_empty_returns_none() -> None:
    """Returns None when no baud rates are provided."""
    assert _parse_baud_rates("") is None


def test_parse_scenarios_with_values() -> None:
    """Parses comma-separated scenario names."""
    assert _parse_scenarios("echo_burst, mixed_command_burst") == [
        "echo_burst",
        "mixed_command_burst",
    ]


def test_parse_scenarios_empty_returns_none() -> None:
    """Returns None when no scenario names are provided."""
    assert _parse_scenarios(" ") is None


def test_latest_new_file_returns_newest_created_path(tmp_path: Path) -> None:
    """Picks newest file from the new-file delta set."""
    existing = tmp_path / "old.json"
    existing.write_text("{}", encoding="utf-8")
    before = {existing}

    file_a = tmp_path / "a.json"
    file_a.write_text("{}", encoding="utf-8")
    file_b = tmp_path / "b.json"
    file_b.write_text("{}", encoding="utf-8")
    after = {existing, file_a, file_b}

    newest = _latest_new_file(before, after)
    assert newest in {str(file_a.resolve()), str(file_b.resolve())}


def test_extract_tester_counters_with_latency_fields() -> None:
    """Extracts sent/received counters from tester-like objects."""
    tester = Mock()
    tester.latency_msg_sent = {0: 1.0, 1: 2.0}
    tester.latency_msg_received = {0: 1.0}
    tester._scenario_results = ["x"]
    counters = _extract_tester_counters(tester)
    assert counters["latency_sent"] == 2
    assert counters["latency_received"] == 1
    assert counters["scenarios_completed"] == 1


def test_event_sink_writes_jsonl(tmp_path: Path) -> None:
    """EventSink writes structured JSON lines to output file."""
    out = tmp_path / "events.jsonl"
    sink = EventSink(
        FeedbackConfig(enabled_stdout=False, jsonl_path=str(out), interval_ms=250)
    )
    sink.emit("heartbeat", mode="latency", elapsed_s=1.2)
    sink.close()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[0])
    assert payload["event"] == "heartbeat"
    assert payload["mode"] == "latency"


def test_write_runner_summary_file_creates_envelope(tmp_path: Path) -> None:
    """Runner summary file is generated using metadata envelope."""
    summary = {"mode": "latency", "result_file": str(tmp_path / "result.json")}
    from runner_cli import __file__ as runner_file

    base = Path(runner_file).parent.parent / "test_results"
    base.mkdir(parents=True, exist_ok=True)
    out_path = _write_runner_summary_file(summary)
    data = json.loads(Path(out_path).read_text(encoding="utf-8"))
    assert data["format_type"] == "runner_summary"
    assert data["payload"]["mode"] == "latency"
