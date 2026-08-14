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

"""Serial interface module."""

from __future__ import annotations

import logging
import queue
import threading
from collections import defaultdict
from enum import Enum
from typing import TYPE_CHECKING, Any

import serial
from cobs import cobs

from checksum import calculate_checksum
from logger_config import setup_logging

if TYPE_CHECKING:
    from collections.abc import Callable

setup_logging()

logger = logging.getLogger(__name__)


class SerialCommand(Enum):
    """Command enum."""

    ECHO_COMMAND = 20
    KEY_COMMAND = 4
    ANALOG_COMMAND = 3
    STATISTICS_STATUS_COMMAND = 23
    TASK_STATUS_COMMAND = 24


class SerialStatistics:
    """
    Serial interface statistics.

    Counters are written by the read thread (``bytes_received``) and the
    processing thread (``commands_received``) while being read by the main
    thread and, under the headless runner, by the heartbeat thread.  Every
    mutation and every read therefore goes through ``_lock``; consumers should
    call :meth:`snapshot` rather than iterating the dictionaries directly.
    """

    def __init__(self) -> None:
        """Initialize statistics."""
        self._lock = threading.Lock()
        self.bytes_received = 0
        self.bytes_sent = 0
        self.commands_sent: dict[int, int] = defaultdict(int)
        self.commands_received: dict[int, int] = defaultdict(int)
        # Frames dropped because the processing queue was saturated.
        self.dropped_frames = 0
        # Frames whose trailing XOR checksum did not match the payload.
        self.checksum_mismatches = 0

    def record_sent(self, command: int, byte_count: int) -> None:
        """Account for one transmitted frame."""
        with self._lock:
            self.bytes_sent += byte_count
            self.commands_sent[command] += 1

    def record_sent_bytes(self, byte_count: int) -> None:
        """Account for raw bytes written outside the framed command path."""
        with self._lock:
            self.bytes_sent += byte_count

    def record_received_bytes(self, byte_count: int) -> None:
        """Account for raw bytes read from the port."""
        with self._lock:
            self.bytes_received += byte_count

    def record_received_command(self, command: int) -> None:
        """Account for one successfully decoded frame."""
        with self._lock:
            self.commands_received[command] += 1

    def record_dropped_frame(self) -> None:
        """Account for one frame discarded because the queue was full."""
        with self._lock:
            self.dropped_frames += 1

    def record_checksum_mismatch(self) -> None:
        """Account for one frame whose trailing checksum did not verify."""
        with self._lock:
            self.checksum_mismatches += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a consistent, plain-dict copy of every counter."""
        with self._lock:
            return {
                "bytes_received": self.bytes_received,
                "bytes_sent": self.bytes_sent,
                "commands_sent": dict(self.commands_sent),
                "commands_received": dict(self.commands_received),
                "dropped_frames": self.dropped_frames,
                "checksum_mismatches": self.checksum_mismatches,
            }


class SerialInterface:
    """Interface to communicate with serial port."""

    BUFFER_HIGH_WATER = 768  # 75% of max buffer size
    BUFFER_LOW_WATER = 256  # 25% of max buffer size
    MAX_BUFFER_SIZE = 1024
    # Upper bound on undelivered frames.  Keeps a stalled or dead consumer from
    # growing the queue without limit while the device floods the port.
    MAX_QUEUE_SIZE = 10000
    # Longest a shutdown will wait on a worker thread before giving up, so a
    # wedged read thread cannot hang a headless run forever.
    JOIN_TIMEOUT_S = 5.0

    def __init__(
        self,
        port: str,
        baudrate: int,
        timeout: float,
        *,
        verify_checksum: bool = False,
    ) -> None:
        """
        Initialize the serial interface.

        ``verify_checksum`` makes :meth:`_process_complete_message` drop frames
        whose trailing XOR byte does not match the payload.  It defaults to
        ``False`` because it is not settled whether the firmware appends a
        checksum to its *replies*: ``command_mode`` logs a received-vs-computed
        pair as if it does, while ``regression_test`` compares the decoded echo
        against the bare payload as if it does not.  Mismatches are counted in
        ``statistics.checksum_mismatches`` regardless, so a run against real
        hardware settles the question before the drop is switched on.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.verify_checksum = verify_checksum
        self.ser = None
        self.stop_event = threading.Event()
        self.message_handler: Callable[[int, bytes, bytes], None] | None = None
        self.message_queue = queue.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self.read_thread = threading.Thread(target=self._read_data)
        self.processing_thread = threading.Thread(target=self._process_messages)
        self.read_thread.daemon = True
        self.processing_thread.daemon = True
        self.buffer = bytearray()
        self.statistics: SerialStatistics = SerialStatistics()
        # Serializes access to the port so concurrent producers (echo publisher,
        # status pollers, raw fault injection) cannot interleave bytes mid-frame.
        self._write_lock = threading.Lock()

    def open(self) -> bool:
        """Open serial port."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                parity=serial.PARITY_NONE,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=True,  # Enable hardware flow control
            )
            self.ser.write_timeout = 0
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self.ser.rts = True  # Initially allow sending
            logger.info("Serial port opened: %s", self.ser)
        except serial.SerialException:
            logger.exception("Error opening serial port.")
            return False
        else:
            return True

    def close(self) -> None:
        """Close serial port, waiting a bounded time for the worker threads."""
        self.stop_event.set()

        # Never join the thread we are running on, and skip threads that were
        # never started -- Thread.join() raises RuntimeError on those.
        current_thread = threading.current_thread()
        for thread in (self.read_thread, self.processing_thread):
            if thread is None or thread is current_thread or not thread.is_alive():
                continue
            thread.join(timeout=self.JOIN_TIMEOUT_S)
            if thread.is_alive():
                logger.warning(
                    "Thread %s did not stop within %.1fs; abandoning it",
                    thread.name,
                    self.JOIN_TIMEOUT_S,
                )

        if self.ser:
            self.ser.close()
            logger.info("Serial port closed")

    def set_baudrate(self, baudrate: int) -> bool:
        """Close, change baud rate, reopen the port, and restart read threads."""
        self.close()
        self.baudrate = baudrate
        self.buffer.clear()
        if not self.open():
            return False
        self.start_reading()
        logger.info("Baud rate changed to %d", baudrate)
        return True

    def send_command(self, hex_data: str) -> None:
        """Send command."""
        if len(hex_data) % 2 != 0:
            logger.info("Invalid hex data")
            return

        payload = bytes.fromhex(hex_data)
        self.write(payload)

    def write(self, data: bytes) -> None:
        """Calculate the checksum and append it to the payload."""
        try:
            if self.ser:
                if not self.stop_event.is_set():
                    checksum = calculate_checksum(data)
                    payload_with_checksum = data + checksum
                    message = cobs.encode(payload_with_checksum) + b"\x00"
                    command: int = data[1] & 0x1F
                    with self._write_lock:
                        bytes_writen = self.ser.write(message) or 0
                    self.statistics.record_sent(command, bytes_writen)
                    logger.info("Published (encoded) `%s`", message)
            else:
                logger.info("Serial port not open")
        except IndexError:
            logger.exception("Error processing message to send")
        except serial.SerialTimeoutException:
            # write_timeout is 0 (non-blocking), so a saturated output buffer
            # surfaces here.  Drop the frame rather than abort the caller's run.
            logger.warning("Write timed out; output buffer full, frame dropped")
        except serial.SerialException:
            logger.exception("Serial error while writing; frame dropped")

    def write_raw(self, data: bytes) -> None:
        """
        Write bytes verbatim, bypassing COBS framing and the checksum.

        Used by fault-injection and noise scenarios that must put malformed
        sequences on the wire.  Takes the same lock as :meth:`write` so raw
        injection cannot interleave with framed traffic.
        """
        if not self.ser:
            logger.info("Serial port not open")
            return
        try:
            with self._write_lock:
                bytes_written = self.ser.write(data) or 0
                self.ser.flush()
            # Raw frames carry no command id, so only the byte counter moves.
            self.statistics.record_sent_bytes(bytes_written)
            logger.info("Wrote %d raw bytes", bytes_written)
        except serial.SerialTimeoutException:
            logger.warning("Raw write timed out; output buffer full")
        except serial.SerialException:
            logger.exception("Serial error while writing raw bytes")

    def flush(self) -> None:
        """Flush the serial output buffer, blocking until all data is transmitted."""
        if self.ser:
            self.ser.flush()

    def is_open(self) -> bool:
        """Check if connection is open."""
        return self.ser is not None and self.ser.is_open

    def set_message_handler(self, handler: Callable[[int, bytes, bytes], None]) -> None:
        """Set message handler."""
        self.message_handler = handler

    def start_reading(self) -> None:
        """Start reading thread and processing thread."""
        self.stop_event.clear()
        # Python threads cannot be restarted; create new ones
        self.read_thread = threading.Thread(target=self._read_data)
        self.processing_thread = threading.Thread(target=self._process_messages)
        self.read_thread.daemon = True
        self.processing_thread.daemon = True
        self.read_thread.start()
        self.processing_thread.start()

    def _process_messages(self) -> None:
        """Process messages from the queue."""
        logger.info("Start processing message thread...")
        while not self.stop_event.is_set():
            try:
                byte_string = self.message_queue.get(timeout=0.1)
                self._process_complete_message(byte_string)
            except queue.Empty:
                continue

    def _process_complete_message(self, byte_string: bytes) -> None:
        """Process a complete message."""
        try:
            decoded_data: bytes = cobs.decode(byte_string)
            command: int = decoded_data[1] & 0x1F
            if not self._checksum_ok(decoded_data):
                self.statistics.record_checksum_mismatch()
                logger.warning(
                    "Checksum mismatch on frame `%s`%s",
                    byte_string.hex(),
                    " (dropped)" if self.verify_checksum else " (accepted)",
                )
                if self.verify_checksum:
                    return
            # Add a counter of commands
            self.statistics.record_received_command(command)
            if self.message_handler:
                self.message_handler(command, decoded_data, byte_string)
        except (IndexError, cobs.DecodeError):  # fmt: skip
            logger.exception("Error processing message")

    @staticmethod
    def _checksum_ok(decoded_data: bytes) -> bool:
        """Return whether the trailing XOR byte matches the preceding payload."""
        if len(decoded_data) < 2:  # noqa: PLR2004  # payload + checksum minimum
            return False
        return calculate_checksum(decoded_data[:-1]) == decoded_data[-1:]

    def _enqueue_message(self, frame: bytes) -> None:
        """Queue a complete frame, dropping it if the consumer is saturated."""
        try:
            self.message_queue.put_nowait(frame)
        except queue.Full:
            # Never block the read thread on a stalled consumer: shed the frame
            # and keep draining the port.
            self.statistics.record_dropped_frame()
            logger.warning(
                "Message queue full (%d frames); dropping frame",
                self.MAX_QUEUE_SIZE,
            )

    def _handle_received_data(self, data: bytes, max_message_size: int) -> None:
        """Handle received data and put complete messages in the queue."""
        self.statistics.record_received_bytes(len(data))

        # Update RTS based on buffer size
        if self.ser:
            if len(self.buffer) > self.BUFFER_HIGH_WATER:
                self.ser.rts = False  # Stop sender
            elif len(self.buffer) < self.BUFFER_LOW_WATER:
                self.ser.rts = True  # Allow sender to send

        for byte in data:
            if byte == 0:  # COBS packet delimiter
                if self.buffer:  # Only process if we have a complete packet
                    self._enqueue_message(bytes(self.buffer))
                    self.buffer.clear()  # Clear buffer only after processing
            else:
                self.buffer.append(byte)

                # Protection against malformed packets
                if len(self.buffer) > max_message_size:
                    logger.warning(
                        "Message exceeded maximum size (%d bytes), discarding",
                        max_message_size,
                    )
                    self.buffer.clear()  # Clear buffer if it exceeds max size

    def _read_data(self) -> None:
        """
        Read thread.

        Reads data from the serial port and processes COBS-encoded messages.
        A zero byte (0x00) is used as a packet delimiter in COBS encoding.
        """
        max_message_size = 1024  # Maximum allowed message size
        logger.info("Starting read thread...")

        try:
            while not self.stop_event.is_set():
                if not self.ser:
                    logger.error("Serial port disconnected")
                    break

                # Read available data
                data = self.ser.read(self.ser.in_waiting or 1)
                if data:
                    self._handle_received_data(data, max_message_size)

        except serial.SerialException:
            logger.exception("Serial port error")
        except Exception:
            logger.exception("Unexpected error in read thread")
        finally:
            self.stop_event.set()
            # Don't call self.close() here, just close the serial port if needed
            if self.ser and self.ser.is_open:
                self.ser.close()
                logger.info("Serial port closed from read thread")
            logger.info("Read thread stopped")
