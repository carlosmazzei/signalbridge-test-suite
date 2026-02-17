"""Tests for src/serial_interface.py."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

import serial
from cobs import cobs

from serial_interface import SerialCommand, SerialInterface

if TYPE_CHECKING:
    import pytest


def make_interface() -> SerialInterface:
    """Make a SerialInterface instance for testing."""
    return SerialInterface(port="COM1", baudrate=115200, timeout=0.1)


def test_open_success() -> None:
    """Test successful open of serial port."""
    si = make_interface()

    ser_mock = Mock()
    ser_mock.is_open = True
    with patch("serial_interface.serial.Serial", return_value=ser_mock):
        ok = si.open()
    assert ok is True
    assert si.ser is ser_mock
    assert ser_mock.write_timeout == 0
    ser_mock.reset_input_buffer.assert_called_once()
    ser_mock.reset_output_buffer.assert_called_once()
    assert ser_mock.rts is True


def test_open_failure() -> None:
    """Test failed open of serial port."""
    si = make_interface()
    with patch("serial_interface.serial.Serial", side_effect=serial.SerialException):
        ok = si.open()
    assert ok is False


def test_is_open_states() -> None:
    """Test is_open property reflects serial port state."""
    si = make_interface()
    assert si.is_open() is False
    ser_mock = Mock()
    ser_mock.is_open = True
    si.ser = ser_mock
    assert si.is_open() is True
    ser_mock.is_open = False
    assert si.is_open() is False


def test_send_command_invalid_hex_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Test sending invalid hex command logs error."""
    si = make_interface()
    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("serial_interface")
        logger.addHandler(caplog.handler)
        si.send_command("ABC")  # odd-length
        logger.removeHandler(caplog.handler)
    assert "Invalid hex data" in caplog.text


def test_send_command_valid_calls_write() -> None:
    """Test sending valid hex command calls write with correct bytes."""
    si = make_interface()
    with patch.object(SerialInterface, "write") as mock_write:
        si.send_command("0014")  # 0x00, 0x14
    mock_write.assert_called_once_with(bytes.fromhex("0014"))


def test_write_without_ser_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Test write when serial port is not open logs info."""
    si = make_interface()
    si.ser = None
    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("serial_interface")
        logger.addHandler(caplog.handler)
        si.write(b"\x00\x14")
        logger.removeHandler(caplog.handler)
    assert "Serial port not open" in caplog.text


def test_write_updates_stats_and_calls_serial() -> None:
    """Test write updates statistics and calls serial write."""
    si = make_interface()
    ser_mock = Mock()
    # bytes_written equals actual message length passed
    ser_mock.write.side_effect = len
    si.ser = ser_mock

    # command is data[1] & 0x1F -> 0x14 -> 20
    payload = b"\x00" + bytes([SerialCommand.ECHO_COMMAND.value]) + b"abc"
    si.write(payload)

    # bytes_sent updated and command count incremented
    assert si.statistics.bytes_sent > 0
    assert si.statistics.commands_sent[SerialCommand.ECHO_COMMAND.value] == 1
    # Published encoded message was sent to serial
    ser_mock.write.assert_called_once()


def test_write_with_stop_event_set_does_nothing() -> None:
    """Test write does nothing if stop event is set."""
    si = make_interface()
    ser_mock = Mock()
    si.ser = ser_mock
    si.stop_event.set()
    si.write(b"\x00\x14")
    ser_mock.write.assert_not_called()


def test_write_index_error_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Test write with too-short message logs error."""
    si = make_interface()
    ser_mock = Mock()
    ser_mock.write.side_effect = len
    si.ser = ser_mock

    with caplog.at_level(logging.ERROR):
        logger = logging.getLogger("serial_interface")
        logger.addHandler(caplog.handler)
        si.write(b"\x00")  # too short to index data[1]
        logger.removeHandler(caplog.handler)
    assert "Error processing message to send" in caplog.text


def test_process_complete_message_success_calls_handler() -> None:
    """Test processing a complete message successfully calls the handler."""
    si = make_interface()
    called: dict[str, Any] = {}

    def handler(command: int, decoded: bytes, raw: bytes) -> None:
        called["cmd"] = command
        called["decoded"] = decoded
        called["raw"] = raw

    si.set_message_handler(handler)
    decoded = b"\xaa" + bytes([SerialCommand.KEY_COMMAND.value]) + b"XYZ"
    raw = cobs.encode(decoded)
    si._process_complete_message(raw)

    assert called["cmd"] == SerialCommand.KEY_COMMAND.value
    assert called["decoded"] == decoded
    assert called["raw"] == raw
    assert si.statistics.commands_received[SerialCommand.KEY_COMMAND.value] == 1


def test_process_complete_message_decode_error_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test processing a message that fails COBS decoding logs error."""
    si = make_interface()
    with (
        patch("serial_interface.cobs.decode", side_effect=cobs.DecodeError),
        caplog.at_level(logging.ERROR),
    ):
        logger = logging.getLogger("serial_interface")
        logger.addHandler(caplog.handler)
        si._process_complete_message(b"\x01\x02")
        logger.removeHandler(caplog.handler)
    assert "Error processing message" in caplog.text


def test_handle_received_data_queue_and_rts_toggle() -> None:
    """Test handling received data queues messages and toggles RTS based on buffer."""
    si = make_interface()
    # Shrink watermarks for the test
    si.BUFFER_HIGH_WATER = 3  # pyright: ignore[reportAttributeAccessIssue]
    si.BUFFER_LOW_WATER = 1  # pyright: ignore[reportAttributeAccessIssue]
    ser_mock = Mock()
    ser_mock.rts = True
    si.ser = ser_mock

    # Pre-fill buffer beyond high watermark so the first check disables RTS
    si.buffer = bytearray(b"XXXX")
    si._handle_received_data(
        b"\x00", max_message_size=100
    )  # Clear buffer, queue 'XXXX'
    assert ser_mock.rts is False
    assert si.buffer == bytearray()

    # Next call sees buffer below low watermark, enabling RTS
    si._handle_received_data(b"", max_message_size=100)
    assert ser_mock.rts is True

    # Send a valid message (COBS encoded + delimiter) and ensure it lands in queue
    msg = cobs.encode(b"hi")
    si._handle_received_data(msg + b"\x00", max_message_size=100)
    # First queued item was the prefill ('XXXX'), discard it
    first = si.message_queue.get(timeout=0.5)
    assert first == b"XXXX"
    out = si.message_queue.get(timeout=0.5)
    assert out == msg
    assert si.statistics.bytes_received >= len(msg) + 1


def test_handle_received_data_max_size_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling received data that exceeds max size logs warning."""
    si = make_interface()
    si.ser = Mock()
    with caplog.at_level(logging.WARNING):
        logger = logging.getLogger("serial_interface")
        logger.addHandler(caplog.handler)
        # Exceed max_message_size to trigger warning and buffer clear
        si._handle_received_data(b"ABCDE", max_message_size=3)
        logger.removeHandler(caplog.handler)
    assert "Message exceeded maximum size" in caplog.text
    # After clearing on overflow, the remaining byte ('E') is appended
    assert si.buffer == bytearray(b"E")


def test_read_data_disconnected_path(caplog: pytest.LogCaptureFixture) -> None:
    """Test read data when serial port is disconnected."""
    si = make_interface()
    si.ser = None
    with caplog.at_level(logging.ERROR):
        logger = logging.getLogger("serial_interface")
        logger.addHandler(caplog.handler)
        si._read_data()
        logger.removeHandler(caplog.handler)
    assert "Serial port disconnected" in caplog.text
    assert si.stop_event.is_set()


def test_close_joins_threads_and_closes_ser() -> None:
    """Test close method joins threads and closes serial port."""
    si = make_interface()
    # Replace threads with mocks that have join
    si.read_thread = Mock()
    si.processing_thread = Mock()
    ser_mock = Mock()
    ser_mock.is_open = True
    si.ser = ser_mock

    si.close()
    si.read_thread.join.assert_called_once()
    si.processing_thread.join.assert_called_once()
    ser_mock.close.assert_called_once()


def test_set_baudrate_success() -> None:
    """set_baudrate closes, reopens at new rate, and restarts threads."""
    si = make_interface()
    # Replace threads with mocks so close() can join them
    si.read_thread = Mock()
    si.processing_thread = Mock()
    si.ser = Mock()

    ser_mock = Mock()
    ser_mock.is_open = True
    with patch("serial_interface.serial.Serial", return_value=ser_mock):
        result = si.set_baudrate(921600)

    assert result is True
    assert si.baudrate == 921600  # noqa: PLR2004


def test_set_baudrate_failure() -> None:
    """set_baudrate returns False when reopen fails."""
    si = make_interface()
    si.read_thread = Mock()
    si.processing_thread = Mock()
    si.ser = Mock()

    with patch("serial_interface.serial.Serial", side_effect=serial.SerialException):
        result = si.set_baudrate(921600)

    assert result is False
    assert si.baudrate == 921600  # noqa: PLR2004
