"""Tests for the KeypadAdcMonitor module."""

from __future__ import annotations

import threading
import time
from unittest.mock import Mock, patch

import pytest
from rich.table import Table

from keypad_adc_monitor import (
    ADC_HISTORY_SIZE,
    KEYPAD_EVENT_HISTORY,
    KeypadAdcMonitor,
)
from serial_interface import SerialCommand, SerialInterface


@pytest.fixture
def mock_serial() -> Mock:
    """Return a mock SerialInterface."""
    ser = Mock(spec=SerialInterface)
    ser.baudrate = 115200
    return ser


@pytest.fixture
def monitor(mock_serial: Mock) -> KeypadAdcMonitor:
    """Return a KeypadAdcMonitor backed by a mock serial interface."""
    return KeypadAdcMonitor(mock_serial)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adc_msg(channel: int, value: int) -> bytes:
    """Build a minimal decoded_data bytes object for an ADC message."""
    high = (value >> 8) & 0xFF
    low = value & 0xFF
    # decoded_data layout: [0]=id_high [1]=id_low|cmd [2]=length [3]=channel [4]=high [5]=low
    return bytes([0x00, 0x03, 0x03, channel, high, low])


def _make_key_msg(col: int, row: int, state: int) -> bytes:
    """Build a minimal decoded_data bytes object for a KEY message."""
    key_byte = ((col & 0x0F) << 4) | ((row & 0x07) << 1) | (state & 0x01)
    return bytes([0x00, 0x04, 0x01, key_byte])


# ---------------------------------------------------------------------------
# ADC message handling
# ---------------------------------------------------------------------------


def test_handle_adc_message_stores_value(monitor: KeypadAdcMonitor) -> None:
    """First ADC message for a channel creates a history entry."""
    msg = _make_adc_msg(channel=0, value=1024)
    monitor.handle_message(SerialCommand.ANALOG_COMMAND.value, msg)

    assert 0 in monitor._adc_history
    entries = list(monitor._adc_history[0])
    assert len(entries) == 1
    assert entries[0][0] == 1024


def test_handle_adc_message_history_limit(monitor: KeypadAdcMonitor) -> None:
    """History per channel is capped at ADC_HISTORY_SIZE."""
    for i in range(ADC_HISTORY_SIZE + 5):
        monitor.handle_message(
            SerialCommand.ANALOG_COMMAND.value, _make_adc_msg(2, i * 10)
        )

    assert len(monitor._adc_history[2]) == ADC_HISTORY_SIZE


def test_handle_adc_multiple_channels(monitor: KeypadAdcMonitor) -> None:
    """Two ADC channels are tracked independently."""
    monitor.handle_message(SerialCommand.ANALOG_COMMAND.value, _make_adc_msg(0, 100))
    monitor.handle_message(SerialCommand.ANALOG_COMMAND.value, _make_adc_msg(1, 200))
    monitor.handle_message(SerialCommand.ANALOG_COMMAND.value, _make_adc_msg(0, 150))

    assert next(iter(monitor._adc_history[0]))[0] == 100
    assert list(monitor._adc_history[0])[1][0] == 150
    assert next(iter(monitor._adc_history[1]))[0] == 200


# ---------------------------------------------------------------------------
# Keypad message handling
# ---------------------------------------------------------------------------


def test_handle_key_message_pressed(monitor: KeypadAdcMonitor) -> None:
    """Pressed keypad event is stored with correct col/row/state."""
    msg = _make_key_msg(col=2, row=3, state=1)
    monitor.handle_message(SerialCommand.KEY_COMMAND.value, msg)

    events = list(monitor._keypad_events)
    assert len(events) == 1
    col, row, state, _ = events[0]
    assert col == 2
    assert row == 3
    assert state == 1


def test_handle_key_message_released(monitor: KeypadAdcMonitor) -> None:
    """Released keypad event stores state=0."""
    msg = _make_key_msg(col=1, row=0, state=0)
    monitor.handle_message(SerialCommand.KEY_COMMAND.value, msg)

    events = list(monitor._keypad_events)
    assert events[0][2] == 0


def test_handle_key_message_odd_column(monitor: KeypadAdcMonitor) -> None:
    """Row is decoded correctly when column is odd (regression for 0x0F mask bug)."""
    msg = _make_key_msg(col=3, row=5, state=1)
    monitor.handle_message(SerialCommand.KEY_COMMAND.value, msg)

    events = list(monitor._keypad_events)
    assert len(events) == 1
    col, row, state, _ = events[0]
    assert col == 3
    assert row == 5
    assert state == 1


@pytest.mark.parametrize(
    ("col", "row", "state"),
    [(c, r, s) for c in (0, 1, 7, 15) for r in (0, 1, 7) for s in (0, 1)],
)
def test_handle_key_message_full_matrix(
    monitor: KeypadAdcMonitor, col: int, row: int, state: int
) -> None:
    """Column (4-bit), row (3-bit), and state decode correctly across the matrix."""
    msg = _make_key_msg(col=col, row=row, state=state)
    monitor.handle_message(SerialCommand.KEY_COMMAND.value, msg)

    events = list(monitor._keypad_events)
    assert len(events) == 1
    decoded_col, decoded_row, decoded_state, _ = events[0]
    assert decoded_col == col
    assert decoded_row == row
    assert decoded_state == state


def test_handle_key_event_history_limit(monitor: KeypadAdcMonitor) -> None:
    """Keypad event log is capped at KEYPAD_EVENT_HISTORY entries."""
    for i in range(KEYPAD_EVENT_HISTORY + 10):
        monitor.handle_message(
            SerialCommand.KEY_COMMAND.value, _make_key_msg(i % 16, 0, 1)
        )

    assert len(monitor._keypad_events) == KEYPAD_EVENT_HISTORY


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_handle_unknown_command_ignored(monitor: KeypadAdcMonitor) -> None:
    """An unrecognised command does not raise and does not modify state."""
    monitor.handle_message(99, bytes([0x00, 0x63, 0x01, 0xAB]))
    assert not monitor._adc_history
    assert not monitor._keypad_events


def test_handle_short_message_ignored(monitor: KeypadAdcMonitor) -> None:
    """A truncated ADC message is handled without crashing."""
    monitor.handle_message(SerialCommand.ANALOG_COMMAND.value, bytes([0x00, 0x03]))
    assert not monitor._adc_history


# ---------------------------------------------------------------------------
# Sparkline
# ---------------------------------------------------------------------------


def test_sparkline_empty() -> None:
    """Empty input returns an empty string."""
    assert KeypadAdcMonitor._sparkline([]) == ""


def test_sparkline_single_value() -> None:
    """A single value always maps to the lowest spark character."""
    result = KeypadAdcMonitor._sparkline([2000])
    assert len(result) == 1


def test_sparkline_full_range() -> None:
    """Min value maps to ▁ and max value maps to █."""
    result = KeypadAdcMonitor._sparkline([0, 4095])
    assert result[0] == "▁"
    assert result[-1] == "█"


def test_sparkline_all_same_value() -> None:
    """All identical values produce the lowest spark character (no division error)."""
    result = KeypadAdcMonitor._sparkline([512, 512, 512])
    assert all(c == "▁" for c in result)


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------


def test_build_adc_table_empty(monitor: KeypadAdcMonitor) -> None:
    """_build_adc_table returns a Table with a placeholder row when no data."""
    table = monitor._build_adc_table()
    assert isinstance(table, Table)


def test_build_adc_table_with_data(monitor: KeypadAdcMonitor) -> None:
    """_build_adc_table returns a Table with one row per active channel."""
    monitor.handle_message(SerialCommand.ANALOG_COMMAND.value, _make_adc_msg(0, 512))
    monitor.handle_message(SerialCommand.ANALOG_COMMAND.value, _make_adc_msg(3, 1024))
    table = monitor._build_adc_table()
    assert isinstance(table, Table)
    assert table.row_count == 2


def test_build_keypad_table_empty(monitor: KeypadAdcMonitor) -> None:
    """_build_keypad_table returns a Table with a placeholder row when no events."""
    table = monitor._build_keypad_table()
    assert isinstance(table, Table)


def test_build_keypad_table_with_data(monitor: KeypadAdcMonitor) -> None:
    """_build_keypad_table returns a Table with one row per event."""
    monitor.handle_message(SerialCommand.KEY_COMMAND.value, _make_key_msg(1, 2, 1))
    monitor.handle_message(SerialCommand.KEY_COMMAND.value, _make_key_msg(1, 2, 0))
    table = monitor._build_keypad_table()
    assert isinstance(table, Table)
    assert table.row_count == 2


# ---------------------------------------------------------------------------
# execute_monitor exits on stop event
# ---------------------------------------------------------------------------


def test_execute_monitor_exits_on_stop_event(
    monitor: KeypadAdcMonitor, mock_serial: Mock
) -> None:
    """execute_monitor terminates when _stop_event is set externally."""
    _ = mock_serial

    def _set_stop_after_delay() -> None:
        time.sleep(0.3)
        monitor._stop_event.set()

    trigger = threading.Thread(target=_set_stop_after_delay, daemon=True)

    with patch("keypad_adc_monitor.console"):
        trigger.start()
        monitor.execute_monitor()
        trigger.join(timeout=2.0)

    assert monitor._stop_event.is_set()


# ---------------------------------------------------------------------------
# Thread safety: concurrent writes from multiple threads
# ---------------------------------------------------------------------------


def test_concurrent_adc_updates_no_race(monitor: KeypadAdcMonitor) -> None:
    """Concurrent ADC messages from multiple threads do not corrupt state."""
    errors: list[Exception] = []

    def _send(channel: int, count: int) -> None:
        try:
            for i in range(count):
                monitor.handle_message(
                    SerialCommand.ANALOG_COMMAND.value, _make_adc_msg(channel, i)
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_send, args=(ch, 50)) for ch in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    for ch in range(4):
        assert len(monitor._adc_history[ch]) <= ADC_HISTORY_SIZE


def test_fmt_ts_returns_string(monitor: KeypadAdcMonitor) -> None:
    """_fmt_ts returns a non-empty string for a valid timestamp."""
    result = monitor._fmt_ts(time.time())
    assert isinstance(result, str)
    assert len(result) > 0
