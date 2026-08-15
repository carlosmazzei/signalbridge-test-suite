# Copyright (C) 2026 SignalBridge contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Tests for src/serial_interface.py."""

from __future__ import annotations

import logging
import queue
import threading
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

import serial
from cobs import cobs

from checksum import calculate_checksum
from serial_interface import SerialCommand, SerialInterface, SerialStatistics

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
    body = b"\xaa" + bytes([SerialCommand.KEY_COMMAND.value]) + b"XYZ"
    decoded = body + calculate_checksum(body)
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
    """Received data is framed into the queue and RTS tracks consumer lag."""
    si = make_interface()
    # Shrink watermarks so the test does not need thousands of frames.
    si.QUEUE_HIGH_WATER = 2  # pyright: ignore[reportAttributeAccessIssue]
    si.QUEUE_LOW_WATER = 1  # pyright: ignore[reportAttributeAccessIssue]
    ser_mock = Mock()
    ser_mock.rts = True
    si.ser = ser_mock

    # Backlog past the high watermark: tell the sender to stop.
    for _ in range(3):
        si.message_queue.put(b"backlog")
    si._handle_received_data(b"", max_message_size=100)
    assert ser_mock.rts is False

    # Consumer catches up below the low watermark: allow sending again.
    while not si.message_queue.empty():
        si.message_queue.get_nowait()
    si._handle_received_data(b"", max_message_size=100)
    assert ser_mock.rts is True

    # A valid message (COBS encoded + delimiter) still lands in the queue.
    msg = cobs.encode(b"hi")
    si._handle_received_data(msg + b"\x00", max_message_size=100)
    out = si.message_queue.get(timeout=0.5)
    assert out == msg
    assert si.statistics.snapshot()["bytes_received"] >= len(msg) + 1


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

        body = b"\xaa" + bytes([SerialCommand.ECHO_COMMAND.value]) + b"payload"
        decoded = body + calculate_checksum(body)
        raw = cobs.encode(decoded)
        si.message_queue.put(raw)

        si._process_messages()

        assert called["cmd"] == SerialCommand.ECHO_COMMAND.value
        assert called["decoded"] == decoded
        assert called["raw"] == raw


class TestFlowControlBoundaries:
    """RTS reacts to queue depth, at the exact watermark boundaries."""

    @staticmethod
    def _with_pending(pending: int, *, rts: bool) -> tuple[SerialInterface, Mock]:
        si = make_interface()
        ser_mock = Mock()
        ser_mock.rts = rts
        si.ser = ser_mock
        for _ in range(pending):
            si.message_queue.put(b"x")
        return si, ser_mock

    def test_queue_at_high_water_does_not_deassert_rts(self) -> None:
        """Comparison is '>' so exactly at the watermark must not stop the sender."""
        si, ser_mock = self._with_pending(SerialInterface.QUEUE_HIGH_WATER, rts=True)
        si._handle_received_data(b"", max_message_size=2048)
        assert ser_mock.rts is True

    def test_queue_above_high_water_deasserts_rts(self) -> None:
        """One frame past the watermark applies backpressure."""
        si, ser_mock = self._with_pending(
            SerialInterface.QUEUE_HIGH_WATER + 1, rts=True
        )
        si._handle_received_data(b"", max_message_size=2048)
        assert ser_mock.rts is False

    def test_queue_at_low_water_does_not_assert_rts(self) -> None:
        """Comparison is '<' so exactly at the watermark must not release yet."""
        si, ser_mock = self._with_pending(SerialInterface.QUEUE_LOW_WATER, rts=False)
        si._handle_received_data(b"", max_message_size=2048)
        assert ser_mock.rts is False

    def test_queue_below_low_water_asserts_rts(self) -> None:
        """Once the consumer catches up, the sender is released."""
        si, ser_mock = self._with_pending(
            SerialInterface.QUEUE_LOW_WATER - 1, rts=False
        )
        si._handle_received_data(b"", max_message_size=2048)
        assert ser_mock.rts is True

    def test_ordinary_frame_never_engages_flow_control(self) -> None:
        """
        The regression this fix targets.

        Watermarks used to be compared against ``self.buffer``, the partial-frame
        accumulator that is cleared at every delimiter. A normal ~12-byte frame
        never came close to 768 bytes, so RTS effectively never engaged.
        """
        si = make_interface()
        ser_mock = Mock()
        ser_mock.rts = True
        si.ser = ser_mock

        frame = cobs.encode(b"\x00\x34\x02\x01\x02") + b"\x00"
        for _ in range(50):
            si._handle_received_data(frame, max_message_size=2048)

        # 50 undelivered frames is well below the queue watermark: no backpressure.
        assert ser_mock.rts is True
        assert si.message_queue.qsize() == 50
        # And the accumulator is empty between frames, which is why it was useless
        # as a backpressure signal.
        assert si.buffer == bytearray()


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


class TestResilienceFixes:
    """Regression tests for the resilience and thread-safety hardening."""

    def test_close_without_start_reading_does_not_raise(self) -> None:
        """close() must tolerate threads that were never started."""
        si = make_interface()
        si.ser = Mock()
        # Threads are constructed in __init__ but never started; joining an
        # unstarted thread raises RuntimeError, so close() must skip them.
        si.close()
        si.ser.close.assert_called_once()

    def test_close_gives_up_on_wedged_thread(self) -> None:
        """A thread that never stops is abandoned instead of hanging close()."""
        si = make_interface()
        si.ser = Mock()
        stuck = Mock()
        stuck.is_alive.return_value = True
        stuck.name = "stuck-thread"
        si.read_thread = stuck
        si.processing_thread = None  # type: ignore[assignment]

        si.close()

        stuck.join.assert_called_once_with(timeout=SerialInterface.JOIN_TIMEOUT_S)
        si.ser.close.assert_called_once()

    def test_write_swallows_timeout_exception(self) -> None:
        """A full output buffer must not propagate into the caller's loop."""
        si = make_interface()
        ser_mock = Mock()
        ser_mock.write.side_effect = serial.SerialTimeoutException("full")
        si.ser = ser_mock

        si.write(b"\x00\x34\x02\x01\x02")  # must not raise

    def test_write_swallows_serial_exception(self) -> None:
        """A disconnected cable must not propagate into the caller's loop."""
        si = make_interface()
        ser_mock = Mock()
        ser_mock.write.side_effect = serial.SerialException("gone")
        si.ser = ser_mock

        si.write(b"\x00\x34\x02\x01\x02")  # must not raise

    def test_write_raw_bypasses_framing_and_counts_bytes(self) -> None:
        """write_raw puts bytes on the wire verbatim and tracks them."""
        si = make_interface()
        ser_mock = Mock()
        ser_mock.write.side_effect = len
        si.ser = ser_mock

        payload = bytes([0x01] * 26)
        si.write_raw(payload)

        ser_mock.write.assert_called_once_with(payload)
        ser_mock.flush.assert_called_once()
        assert si.statistics.snapshot()["bytes_sent"] == len(payload)

    def test_write_raw_swallows_serial_exception(self) -> None:
        """Raw injection failures are logged, not raised."""
        si = make_interface()
        ser_mock = Mock()
        ser_mock.write.side_effect = serial.SerialException("gone")
        si.ser = ser_mock

        si.write_raw(b"\x01\x02")  # must not raise

    def test_full_queue_drops_frame_instead_of_blocking(self) -> None:
        """A saturated queue sheds frames rather than stalling the read thread."""
        si = make_interface()
        si.message_queue = queue.Queue(maxsize=1)

        si._enqueue_message(b"first")
        si._enqueue_message(b"second")  # dropped, must not block

        assert si.message_queue.qsize() == 1
        assert si.statistics.snapshot()["dropped_frames"] == 1

    def test_checksum_mismatch_dropped_by_default(self) -> None:
        """Verification is on by default, so a corrupt frame is not delivered."""
        si = make_interface()
        assert si.verify_checksum is True
        seen: list[int] = []
        si.set_message_handler(lambda cmd, _d, _r: seen.append(cmd))

        body = bytes([0x00, SerialCommand.KEY_COMMAND.value, 0x02, 0x11])
        frame = cobs.encode(body + b"\xff")  # deliberately wrong checksum
        si._process_complete_message(frame)

        assert seen == []
        assert si.statistics.snapshot()["checksum_mismatches"] == 1
        # A dropped frame must not inflate the received-command counters.
        assert si.statistics.snapshot()["commands_received"] == {}

    def test_checksum_mismatch_dispatched_when_verification_disabled(self) -> None:
        """The opt-out still counts mismatches but keeps delivering frames."""
        si = SerialInterface(
            port="COM1", baudrate=115200, timeout=0.1, verify_checksum=False
        )
        seen: list[int] = []
        si.set_message_handler(lambda cmd, _d, _r: seen.append(cmd))

        body = bytes([0x00, SerialCommand.KEY_COMMAND.value, 0x02, 0x11])
        frame = cobs.encode(body + b"\xff")
        si._process_complete_message(frame)

        assert seen == [SerialCommand.KEY_COMMAND.value]
        assert si.statistics.snapshot()["checksum_mismatches"] == 1

    def test_valid_checksum_dispatched(self) -> None:
        """A correctly checksummed frame passes verification."""
        si = make_interface()
        seen: list[int] = []
        si.set_message_handler(lambda cmd, _d, _r: seen.append(cmd))

        body = bytes([0x00, SerialCommand.KEY_COMMAND.value, 0x02, 0x11])
        frame = cobs.encode(body + calculate_checksum(body))
        si._process_complete_message(frame)

        assert seen == [SerialCommand.KEY_COMMAND.value]
        assert si.statistics.snapshot()["checksum_mismatches"] == 0

    def test_statistics_snapshot_stable_under_concurrent_writes(self) -> None:
        """snapshot() must not raise while another thread adds command keys."""
        stats = SerialStatistics()
        stop = threading.Event()

        def writer() -> None:
            command = 0
            while not stop.is_set():
                stats.record_received_command(command % 32)
                command += 1

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            for _ in range(2000):
                # Iterating the live defaultdict here would raise
                # "dictionary changed size during iteration".
                assert isinstance(stats.snapshot()["commands_received"], dict)
        finally:
            stop.set()
            thread.join(timeout=5)
