"""Serial interface module."""

from __future__ import annotations

import logging
import queue
import threading
from collections import defaultdict
from enum import Enum
from typing import TYPE_CHECKING

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
    """Serial interface statistics."""

    def __init__(self) -> None:
        """Initialize statistics."""
        self.bytes_received = 0
        self.bytes_sent = 0
        self.commands_sent: dict[int, int] = defaultdict(int)
        self.commands_received: dict[int, int] = defaultdict(int)


class SerialInterface:
    """Interface to communicate with serial port."""

    BUFFER_HIGH_WATER = 768  # 75% of max buffer size
    BUFFER_LOW_WATER = 256  # 25% of max buffer size
    MAX_BUFFER_SIZE = 1024

    def __init__(self, port: str, baudrate: int, timeout: float) -> None:
        """Initialize the serial interface."""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.stop_event = threading.Event()
        self.message_handler: Callable[[int, bytes, bytes], None] | None = None
        self.message_queue = queue.Queue()
        self.read_thread = threading.Thread(target=self._read_data)
        self.processing_thread = threading.Thread(target=self._process_messages)
        self.read_thread.daemon = True
        self.processing_thread.daemon = True
        self.buffer = bytearray()
        self.statistics: SerialStatistics = SerialStatistics()

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
        """Close serial port."""
        self.stop_event.set()

        # Only attempt to join if we're not in the read thread
        current_thread = threading.current_thread()
        if self.read_thread and current_thread != self.read_thread:
            self.read_thread.join()
        if self.processing_thread and current_thread != self.processing_thread:
            self.processing_thread.join()

        if self.ser:
            self.ser.close()
            logger.info("Serial port closed")

    def set_baudrate(self, baudrate: int) -> bool:
        """Close, change baud rate, reopen the port, and restart read threads."""
        self.close()
        self.baudrate = baudrate
        # Python threads cannot be restarted; create new ones
        self.read_thread = threading.Thread(target=self._read_data)
        self.processing_thread = threading.Thread(target=self._process_messages)
        self.read_thread.daemon = True
        self.processing_thread.daemon = True
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
                    bytes_writen = self.ser.write(message) or 0
                    self.statistics.bytes_sent += bytes_writen
                    command: int = data[1] & 0x1F
                    self.statistics.commands_sent[command] += 1
                    logger.info("Published (encoded) `%s`", message)
            else:
                logger.info("Serial port not open")
        except IndexError:
            logger.exception("Error processing message to send")

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
            # Add a counter of commands
            self.statistics.commands_received[command] += 1
            if self.message_handler:
                self.message_handler(command, decoded_data, byte_string)
        except IndexError, cobs.DecodeError:
            logger.exception("Error processing message")

    def _handle_received_data(self, data: bytes, max_message_size: int) -> None:
        """Handle received data and put complete messages in the queue."""
        self.statistics.bytes_received += len(data)

        # Update RTS based on buffer size
        if self.ser:
            if len(self.buffer) > self.BUFFER_HIGH_WATER:
                self.ser.rts = False  # Stop sender
            elif len(self.buffer) < self.BUFFER_LOW_WATER:
                self.ser.rts = True  # Allow sender to send

        for byte in data:
            if byte == 0:  # COBS packet delimiter
                if self.buffer:  # Only process if we have a complete packet
                    self.message_queue.put(bytes(self.buffer))
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
