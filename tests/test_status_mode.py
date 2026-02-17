"""Tests for src/status_mode.py."""

from __future__ import annotations

import logging
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from base_test import STATISTICS_HEADER_BYTES
from serial_interface import SerialCommand
from status_mode import (
    _TASK_INDEX_BY_NAME,
    StatusMode,
)

if TYPE_CHECKING:
    import pytest


class DummyStats:
    """Dummy statistics object for testing."""

    def __init__(self) -> None:
        """Initialize dummy statistics."""
        self.bytes_received = 0
        self.bytes_sent = 0
        self.commands_sent: dict[int, int] = {}
        self.commands_received: dict[int, int] = {}


def make_status_mode() -> StatusMode:
    """Make a StatusMode instance for testing."""
    ser = SimpleNamespace(write=Mock(), statistics=DummyStats())
    return StatusMode(ser=ser)  # type: ignore[arg-type]


def test_handle_message_updates_statistics(caplog: pytest.LogCaptureFixture) -> None:
    """Test handling a statistics status message updates the correct item."""
    sm = make_status_mode()
    idx = 0  # queue_send_error index from STATISTICS_ITEMS
    value = 123456
    payload = bytes([0x00, 0x00, 0x00, idx]) + value.to_bytes(4, "big")

    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("status_mode")
        logger.addHandler(caplog.handler)
        sm.handle_message(SerialCommand.STATISTICS_STATUS_COMMAND.value, payload)
        logger.removeHandler(caplog.handler)

    item = sm.error_items[idx]
    assert item.value == value
    assert item.last_updated != 0
    assert f"{item.message} value updated to {value}" in caplog.text


def test_handle_message_updates_task_fields(caplog: pytest.LogCaptureFixture) -> None:
    """Test handling a task status message updates the correct task fields."""
    sm = make_status_mode()
    idx = _TASK_INDEX_BY_NAME["idle_task"]
    abs_time = 3_210_000
    perc_time = 42
    hwm = 777
    # command byte array indices expected: 3=index, 4-7 abs, 8-11 perc, 12-15 hwm
    payload = (
        bytes([0x00, 0x00, 0x00, idx])
        + abs_time.to_bytes(4, "big")
        + perc_time.to_bytes(4, "big")
        + hwm.to_bytes(4, "big")
    )

    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("status_mode")
        logger.addHandler(caplog.handler)
        sm.handle_message(SerialCommand.TASK_STATUS_COMMAND.value, payload)
        logger.removeHandler(caplog.handler)

    t = sm.task_items[idx]
    assert t.absoulute_time == abs_time
    assert t.percent_time == perc_time
    assert t.high_watermark == hwm
    assert t.last_updated != 0
    assert f"[{t.name}] updated" in caplog.text


def test_handle_message_index_error_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Test handling a message with bad index logs error."""
    sm = make_status_mode()
    with caplog.at_level(logging.ERROR):
        logger = logging.getLogger("status_mode")
        logger.addHandler(caplog.handler)
        sm.handle_message(SerialCommand.TASK_STATUS_COMMAND.value, b"\x01\x02")
        logger.removeHandler(caplog.handler)
    assert "Error parsing status command" in caplog.text


def test_status_update_builds_payload_and_writes() -> None:
    """Test status update builds correct payload and calls write."""
    sm = make_status_mode()
    sm._status_update(STATISTICS_HEADER_BYTES, 5)
    # payload should be: header + 0x01 + index
    (payload,), _ = sm.ser.write.call_args  # pyright: ignore[reportAttributeAccessIssue]
    assert payload[:2] == STATISTICS_HEADER_BYTES
    assert payload[2] == 0x01
    assert payload[3] == 5  # noqa: PLR2004


def test_update_statistics_status_requests_all(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test updating statistics status requests all statistics."""
    sm = make_status_mode()
    with (
        patch.object(StatusMode, "_status_update") as upd,
        patch("status_mode.time.sleep", lambda _x: None),
        caplog.at_level(logging.INFO),
    ):
        logger = logging.getLogger("status_mode")
        logger.addHandler(caplog.handler)
        sm._update_statistics_status()
        logger.removeHandler(caplog.handler)

    assert upd.call_count == len(sm.error_items)
    assert "Status request complete" in caplog.text


def test_update_task_status_requests_all(caplog: pytest.LogCaptureFixture) -> None:
    """Test updating task status requests all tasks."""
    sm = make_status_mode()
    with (
        patch.object(StatusMode, "_status_update") as upd,
        patch("status_mode.time.sleep", lambda _x: None),
        caplog.at_level(logging.INFO),
    ):
        logger = logging.getLogger("status_mode")
        logger.addHandler(caplog.handler)
        sm._update_task_status()
        logger.removeHandler(caplog.handler)

    assert upd.call_count == len(sm.task_items)
    assert "Status request complete" in caplog.text


def test_display_statistics_status_outputs_tables(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test displaying statistics status outputs formatted tables."""
    sm = make_status_mode()
    # Prime some values
    first_idx = next(iter(sm.error_items))
    sm.error_items[first_idx].value = 9001
    sm.error_items[first_idx].last_updated = time.time()
    sm.ser.statistics.bytes_sent = 123
    sm.ser.statistics.bytes_received = 456
    sm.ser.statistics.commands_sent = {SerialCommand.ECHO_COMMAND.value: 2}
    sm.ser.statistics.commands_received = {SerialCommand.KEY_COMMAND.value: 3}

    sm._display_statistics_status()
    out = capsys.readouterr().out

    assert "Statistics Status:" in out
    assert "Statistics Counters:" in out
    # Ensure counter name and human-formatted value present
    assert sm.error_items[first_idx].message in out
    assert "9,001" in out
    # Commands stats and totals
    assert "Commands Sent Stastitics:" in out
    assert "ECHO_COMMAND" in out
    assert "2" in out
    assert "Commands Received Stastitics:" in out
    assert "KEY_COMMAND" in out
    assert "3" in out
    assert "Total bytes sent: 123" in out
    assert "Total bytes received: 456" in out


def test_format_time_from_microseconds() -> None:
    """Test formatting time from microseconds to mm:ss:ms string."""
    sm = make_status_mode()
    assert sm.format_time_from_microseconds(0) == "00:00:000"
    # 1 minute, 2 seconds, 345 ms -> total microseconds = 62,345,000
    assert sm.format_time_from_microseconds(62_345_000) == "01:02:345"


def test_display_task_status_outputs_table(capsys: pytest.CaptureFixture[str]) -> None:
    """Test displaying task status outputs formatted table."""
    sm = make_status_mode()
    # Fill some task values
    sm.task_items[_TASK_INDEX_BY_NAME["cdc_task"]].absoulute_time = 10_000
    sm.task_items[_TASK_INDEX_BY_NAME["uart_event_task"]].absoulute_time = 20_000
    sm.task_items[_TASK_INDEX_BY_NAME["idle_task"]].absoulute_time = 30_000
    sm.task_items[_TASK_INDEX_BY_NAME["encoder_read_task"]].absoulute_time = 40_000
    sm.task_items[_TASK_INDEX_BY_NAME["adc_read_task"]].absoulute_time = 50_000
    sm.task_items[_TASK_INDEX_BY_NAME["keypad_task"]].absoulute_time = 60_000
    sm.task_items[_TASK_INDEX_BY_NAME["process_outbound_task"]].absoulute_time = 70_000
    sm.task_items[_TASK_INDEX_BY_NAME["decode_reception_task"]].absoulute_time = 80_000
    sm.task_items[_TASK_INDEX_BY_NAME["cdc_task"]].percent_time = 11
    sm.task_items[_TASK_INDEX_BY_NAME["cdc_task"]].high_watermark = 99

    sm._display_task_status()
    out = capsys.readouterr().out

    # Table headings
    assert "Task Status:" in out
    assert "Absolute Time (mm:ss:ms)" in out
    # A formatted task row (CDC Task)
    assert "CDC Task" in out
    assert "% Time" in out
    assert "99" in out
    # Totals
    assert "Core 0 total time:" in out
    assert "Core 1 total time:" in out


def test_handle_user_choice_dispatch() -> None:
    """Test handling user menu choices dispatches to correct methods."""
    sm = make_status_mode()
    with (
        patch.object(sm, "_update_statistics_status") as upd_stats,
        patch.object(sm, "_update_task_status") as upd_tasks,
    ):
        assert sm._handle_user_choice("1") is True
        upd_stats.assert_called_once()
        assert sm._handle_user_choice("2") is True
        upd_tasks.assert_called_once()
        assert sm._handle_user_choice("3") is True
        assert sm._handle_user_choice("4") is False
        assert sm._handle_user_choice("x") is True


def test_execute_test_exits_on_choice_four() -> None:
    """Test executing test exits when user selects choice 4."""
    sm = make_status_mode()
    with (
        patch.object(sm, "_display_statistics_status"),
        patch.object(sm, "_display_task_status"),
        patch("builtins.input", return_value="4"),
    ):
        sm.execute_test()
