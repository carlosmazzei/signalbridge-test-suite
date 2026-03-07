"""Tests for src/serial_interface.py."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

import serial
from cobs import cobs

from checksum import calculate_checksum
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
    assert si.baudrate == 921600


def test_set_baudrate_failure() -> None:
    """set_baudrate returns False when reopen fails."""
    si = make_interface()
    si.read_thread = Mock()
    si.processing_thread = Mock()
    si.ser = Mock()

    with patch("serial_interface.serial.Serial", side_effect=serial.SerialException):
        result = si.set_baudrate(921600)

    assert result is False
    assert si.baudrate == 921600


class TestOpenSerialParams:
    """Verify serial.Serial() constructor receives exact parameters."""

    def test_open_passes_correct_serial_params(self) -> None:
        """Test that open() passes correct params to serial.Serial()."""
        si = make_interface()
        ser_mock = Mock()
        with patch(
            "serial_interface.serial.Serial", return_value=ser_mock
        ) as mock_ctor:
            si.open()
        mock_ctor.assert_called_once()
        _, kwargs = mock_ctor.call_args
        assert kwargs["port"] == "COM1"
        assert kwargs["baudrate"] == 115200
        assert kwargs["timeout"] == 0.1
        assert kwargs["parity"] == serial.PARITY_NONE
        assert kwargs["bytesize"] == serial.EIGHTBITS
        assert kwargs["stopbits"] == serial.STOPBITS_ONE
        assert kwargs["xonxoff"] is False
        assert kwargs["rtscts"] is True


class TestProcessMessages:
    """Test _process_messages pulls from queue and processes."""

    def test_process_messages_handles_queued_message(self) -> None:
        """Put a COBS-encoded message in the queue and verify processing."""
        si = make_interface()
        called: dict[str, Any] = {}

        def handler(command: int, decoded: bytes, raw: bytes) -> None:
            called["cmd"] = command
            called["decoded"] = decoded
            called["raw"] = raw
            si.stop_event.set()  # Stop after first message

        si.set_message_handler(handler)

        decoded = b"\xaa" + bytes([SerialCommand.ECHO_COMMAND.value]) + b"payload"
        raw = cobs.encode(decoded)
        si.message_queue.put(raw)

        si._process_messages()

        assert called["cmd"] == SerialCommand.ECHO_COMMAND.value
        assert called["decoded"] == decoded
        assert called["raw"] == raw


class TestFlowControlBoundaries:
    """Test _handle_received_data at exact watermark boundaries."""

    def test_buffer_at_high_water_does_not_deassert_rts(self) -> None:
        """
        Buffer size == BUFFER_HIGH_WATER should NOT trigger RTS deassert.

        The code uses '>' (strictly greater), so exactly at the watermark
        should not deassert RTS.
        """
        si = make_interface()
        ser_mock = Mock()
        ser_mock.rts = True
        si.ser = ser_mock

        # Pre-fill buffer to exactly BUFFER_HIGH_WATER
        si.buffer = bytearray(b"X" * si.BUFFER_HIGH_WATER)
        si._handle_received_data(b"\x00", max_message_size=2048)

        # RTS should still be True (not deasserted) because == not >
        assert ser_mock.rts is True

    def test_buffer_at_low_water_does_not_assert_rts(self) -> None:
        """
        Buffer size == BUFFER_LOW_WATER should NOT trigger RTS assert.

        The code uses '<' (strictly less), so exactly at the watermark
        should not reassert RTS.
        """
        si = make_interface()
        ser_mock = Mock()
        ser_mock.rts = False  # Start with RTS deasserted
        si.ser = ser_mock

        # Pre-fill buffer to exactly BUFFER_LOW_WATER
        si.buffer = bytearray(b"X" * si.BUFFER_LOW_WATER)
        si._handle_received_data(b"\x00", max_message_size=2048)

        # RTS should remain False because == not <
        assert ser_mock.rts is False


class TestWriteEncoding:
    """Verify write() produces correct COBS encoding with checksum and delimiter."""

    def test_write_sends_cobs_encoded_with_checksum_and_delimiter(self) -> None:
        """Call write() with known data and verify exact bytes on the wire."""
        si = make_interface()
        ser_mock = Mock()
        ser_mock.write.side_effect = len
        si.ser = ser_mock

        data = b"\x00" + bytes([SerialCommand.ECHO_COMMAND.value]) + b"abc"
        si.write(data)

        # Expected checksum: XOR of all bytes in data
        expected_checksum = calculate_checksum(data)
        payload_with_checksum = data + expected_checksum
        expected_message = cobs.encode(payload_with_checksum) + b"\x00"

        ser_mock.write.assert_called_once_with(expected_message)

        # Verify the delimiter is at the end
        actual_message = ser_mock.write.call_args[0][0]
        assert actual_message[-1:] == b"\x00"

    def test_write_checksum_byte_is_correct(self) -> None:
        """Verify the checksum byte is the XOR of all data bytes."""
        data = b"\x10\x14\x01\x02"
        expected = 0x10 ^ 0x14 ^ 0x01 ^ 0x02
        assert calculate_checksum(data) == bytes([expected])


class TestFlush:
    """Test flush() method."""

    def test_flush_calls_ser_flush(self) -> None:
        """Verify self.ser.flush() is called when self.ser exists."""
        si = make_interface()
        ser_mock = Mock()
        si.ser = ser_mock
        si.flush()
        ser_mock.flush.assert_called_once()

    def test_flush_no_crash_when_ser_is_none(self) -> None:
        """Verify no crash when self.ser is None."""
        si = make_interface()
        si.ser = None
        si.flush()  # Should not raise


class TestReadDataExceptions:
    """Test _read_data exception handling paths."""

    def test_serial_exception_logs_and_sets_stop(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Mock self.ser.read to raise SerialException → verify it logs."""
        si = make_interface()
        ser_mock = Mock()
        ser_mock.in_waiting = 1
        ser_mock.read.side_effect = serial.SerialException("port gone")
        ser_mock.is_open = True
        si.ser = ser_mock

        with caplog.at_level(logging.ERROR):
            logger = logging.getLogger("serial_interface")
            logger.addHandler(caplog.handler)
            si._read_data()
            logger.removeHandler(caplog.handler)

        assert "Serial port error" in caplog.text
        assert si.stop_event.is_set()

    def test_generic_exception_logs_and_sets_stop(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Mock self.ser.read to raise generic Exception → verify it logs."""
        si = make_interface()
        ser_mock = Mock()
        ser_mock.in_waiting = 1
        ser_mock.read.side_effect = RuntimeError("boom")
        ser_mock.is_open = True
        si.ser = ser_mock

        with caplog.at_level(logging.ERROR):
            logger = logging.getLogger("serial_interface")
            logger.addHandler(caplog.handler)
            si._read_data()
            logger.removeHandler(caplog.handler)

        assert "Unexpected error in read thread" in caplog.text
        assert si.stop_event.is_set()


def test_threads_are_daemon() -> None:
    """Verify read_thread and processing_thread are daemon threads."""
    si = make_interface()
    assert si.read_thread.daemon is True
    assert si.processing_thread.daemon is True
