"""Tests for src/status_mode.py."""

from __future__ import annotations

import datetime
import logging
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from base_test import STATISTICS_HEADER_BYTES
from serial_interface import SerialCommand, SerialInterface
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
    assert t.absolute_time == abs_time
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
    assert payload[3] == 5


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

    assert "Statistics Counters" in out
    # Ensure counter name and human-formatted value present
    assert sm.error_items[first_idx].message in out
    assert "9,001" in out
    # Commands stats and totals
    assert "Commands Sent" in out
    assert "ECHO_COMMAND" in out
    assert "2" in out
    assert "Commands Received" in out
    assert "KEY_COMMAND" in out
    assert "3" in out
    assert "Total bytes sent:" in out
    assert "123" in out
    assert "Total bytes received:" in out
    assert "456" in out


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
    sm.task_items[_TASK_INDEX_BY_NAME["cdc_task"]].absolute_time = 10_000
    sm.task_items[_TASK_INDEX_BY_NAME["uart_event_task"]].absolute_time = 20_000
    sm.task_items[_TASK_INDEX_BY_NAME["idle_task"]].absolute_time = 30_000
    sm.task_items[_TASK_INDEX_BY_NAME["adc_read_task"]].absolute_time = 50_000
    sm.task_items[_TASK_INDEX_BY_NAME["keypad_task"]].absolute_time = 60_000
    sm.task_items[_TASK_INDEX_BY_NAME["process_outbound_task"]].absolute_time = 70_000
    sm.task_items[_TASK_INDEX_BY_NAME["decode_reception_task"]].absolute_time = 80_000
    sm.task_items[_TASK_INDEX_BY_NAME["cdc_task"]].percent_time = 11
    sm.task_items[_TASK_INDEX_BY_NAME["cdc_task"]].high_watermark = 99

    sm._display_task_status()
    out = capsys.readouterr().out

    # Table headings
    assert "Task Status" in out
    assert "Abs Time" in out
    # A formatted task row (CDC Task)
    assert "CDC Task" in out
    assert "% Time" in out
    assert "99" in out
    # Totals
    assert "Core 0 total time" in out
    assert "Core 1 total time" in out


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


# ---------------------------------------------------------------------------
# Additional mutation-testing coverage
# ---------------------------------------------------------------------------


class TestFmtTimestamp:
    """Tests for the _fmt_timestamp static helper."""

    def test_zero_returns_na(self) -> None:
        """Passing 0 should return 'N/A'."""
        assert StatusMode._fmt_timestamp(0) == "N/A"

    def test_nonzero_returns_formatted_string(self) -> None:
        """A known nonzero timestamp produces the expected datetime string."""
        ts = 1700000000
        expected = datetime.datetime.fromtimestamp(ts, tz=datetime.UTC).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        assert StatusMode._fmt_timestamp(ts) == expected

    def test_negative_zero_returns_na(self) -> None:
        """Passing 0.0 (float zero) should also return 'N/A'."""
        assert StatusMode._fmt_timestamp(0.0) == "N/A"


def test_handle_message_unknown_index() -> None:
    """Calling handle_message with an unknown status_index causes no crash or change."""
    sm = make_status_mode()

    # Snapshot originals
    orig_error_values = {k: v.value for k, v in sm.error_items.items()}
    orig_task_abs = {k: v.absolute_time for k, v in sm.task_items.items()}

    unknown_idx = 0xFF  # not in error_items or task_items

    # --- statistics branch with unknown index ---
    stat_payload = bytes([0x00, 0x00, 0x00, unknown_idx]) + (100).to_bytes(4, "big")
    sm.handle_message(SerialCommand.STATISTICS_STATUS_COMMAND.value, stat_payload)

    assert {k: v.value for k, v in sm.error_items.items()} == orig_error_values

    # --- task branch with unknown index ---
    task_payload = (
        bytes([0x00, 0x00, 0x00, unknown_idx])
        + (200).to_bytes(4, "big")
        + (10).to_bytes(4, "big")
        + (5).to_bytes(4, "big")
    )
    sm.handle_message(SerialCommand.TASK_STATUS_COMMAND.value, task_payload)

    assert {k: v.absolute_time for k, v in sm.task_items.items()} == orig_task_abs


def test_display_task_status_shows_computed_totals(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify Core 0 / Core 1 numeric totals appear in the rendered output."""
    sm = make_status_mode()

    # Assign known microsecond values to every task
    sm.task_items[_TASK_INDEX_BY_NAME["cdc_task"]].absolute_time = 1_000_000
    sm.task_items[_TASK_INDEX_BY_NAME["cdc_write_task"]].absolute_time = 500_000
    sm.task_items[_TASK_INDEX_BY_NAME["uart_event_task"]].absolute_time = 2_000_000
    sm.task_items[_TASK_INDEX_BY_NAME["led_status_task"]].absolute_time = 100_000
    sm.task_items[_TASK_INDEX_BY_NAME["idle_task"]].absolute_time = 3_000_000
    sm.task_items[_TASK_INDEX_BY_NAME["adc_read_task"]].absolute_time = 5_000_000
    sm.task_items[_TASK_INDEX_BY_NAME["keypad_task"]].absolute_time = 6_000_000
    sm.task_items[
        _TASK_INDEX_BY_NAME["process_outbound_task"]
    ].absolute_time = 7_000_000
    sm.task_items[
        _TASK_INDEX_BY_NAME["decode_reception_task"]
    ].absolute_time = 8_000_000
    sm.task_items[_TASK_INDEX_BY_NAME["idle_task"]].high_watermark = 23_400

    sm._display_task_status()
    out = capsys.readouterr().out

    # Core 0 = cdc + cdc_write + uart + led = 1M + 0.5M + 2M + 0.1M = 3_600_000
    # formatted as "3,600,000.000"
    assert "3,600,000.000" in out

    # Core 1 = decode + process + adc + keypad
    # = 8M + 7M + 5M + 6M = 26_000_000
    # formatted as "26,000,000.000"
    assert "26,000,000.000" in out

    # Heap info from idle_task slot should appear
    assert "Min free heap" in out
    assert "23,400 bytes" in out


def test_execute_test_statistics_choice() -> None:
    """Choosing '1' then '4' should call _display_statistics_status and exit."""
    sm = make_status_mode()
    choices = iter(["1", "4"])
    with (
        patch.object(sm, "_display_statistics_status") as disp_stats,
        patch.object(sm, "_display_task_status"),
        patch.object(sm, "_update_statistics_status"),
        patch("builtins.input", side_effect=lambda *_a, **_kw: next(choices)),
    ):
        sm.execute_test()

    # _display_statistics_status is called at the top of each loop iteration
    # Loop runs twice (choice "1" → continue, choice "4" → exit)
    assert disp_stats.call_count == 2


def test_update_statistics_status_sends_correct_header() -> None:
    """Verify _update_statistics_status calls _status_update with STATISTICS_HEADER_BYTES."""
    sm = make_status_mode()
    with (
        patch.object(sm, "_status_update") as upd,
        patch("status_mode.time.sleep", lambda _x: None),
    ):
        sm._update_statistics_status()

    # Every call must use STATISTICS_HEADER_BYTES as the first argument
    for call in upd.call_args_list:
        args, _kwargs = call
        assert args[0] == STATISTICS_HEADER_BYTES


# ---------------------------------------------------------------------------
# Core label helper
# ---------------------------------------------------------------------------


class TestCoreLabel:
    """Tests for the _core_label static helper."""

    def test_core0_label(self) -> None:
        """Core 0 should produce a bright_blue label."""
        result = StatusMode._core_label(0)
        assert "Core 0" in result

    def test_core1_label(self) -> None:
        """Core 1 should produce a bright_magenta label."""
        result = StatusMode._core_label(1)
        assert "Core 1" in result

    def test_unpinned_label(self) -> None:
        """Unpinned core (-1) should produce 'N/A'."""
        result = StatusMode._core_label(-1)
        assert "N/A" in result


# ---------------------------------------------------------------------------
# Task table column content
# ---------------------------------------------------------------------------


def test_display_task_status_shows_core_and_stack_columns(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify the task table includes Core and Stack columns."""
    sm = make_status_mode()
    sm._display_task_status()
    out = capsys.readouterr().out
    assert "Core" in out
    assert "Stack (B)" in out


def test_display_task_status_idle_heap_label(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Idle task row should display its watermark as heap info."""
    sm = make_status_mode()
    sm.task_items[_TASK_INDEX_BY_NAME["idle_task"]].high_watermark = 12_345
    sm._display_task_status()
    out = capsys.readouterr().out
    # Rich strips the [cyan] markup; rendered text contains the value and label
    assert "12,345" in out
    assert "heap" in out


# ---------------------------------------------------------------------------
# Heap info in BaseTest
# ---------------------------------------------------------------------------


def _make_mock_serial() -> Mock:
    """Create a mocked SerialInterface for BaseTest tests."""
    ser = Mock(spec=SerialInterface)
    ser.baudrate = 115200
    return ser


def test_base_test_stores_min_free_heap() -> None:
    """BaseTest should store min_free_heap_bytes when idle task index is received."""
    from base_test import IDLE_TASK_INDEX, BaseTest

    bt = BaseTest(_make_mock_serial())
    heap_value = 23_400
    data = (
        bytes([0x00, 0x00, 0x00, IDLE_TASK_INDEX])
        + (5_000_000).to_bytes(4, "big")
        + (15).to_bytes(4, "big")
        + heap_value.to_bytes(4, "big")
    )
    bt.handle_message(SerialCommand.TASK_STATUS_COMMAND.value, data)
    assert bt._min_free_heap_bytes == heap_value


def test_base_test_snapshot_includes_heap() -> None:
    """Status snapshot should include min_free_heap_bytes."""
    from base_test import BaseTest

    bt = BaseTest(_make_mock_serial())
    bt._min_free_heap_bytes = 42_000

    with (
        patch("base_test.time.sleep", return_value=None),
        patch(
            "base_test.time.perf_counter",
            side_effect=[100.0, 100.0, 200.0, 200.0],
        ),
    ):
        result = bt._request_status_snapshot(timeout_s=1.0)

    assert result["min_free_heap_bytes"] == 42_000
