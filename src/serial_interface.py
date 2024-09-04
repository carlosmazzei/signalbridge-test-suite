import threading
from collections.abc import Callable
from enum import Enum

import serial
from checksum import calculate_checksum
from cobs import cobs
from logger import Logger


class SerialCommand(Enum):
    """Command enum."""

    ECHO_COMMAND = 20
    KEY_COMMAND = 4
    ANALOG_COMMAND = 3


class SerialInterface:
    """Interface to communicate with serial port."""

    def __init__(self, port: str, baudrate: int, timeout: float, logger: Logger):
        """Initialize the serial interface."""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.logger = logger
        self.ser = None
        self.stop_event = threading.Event()
        self.read_thread = None
        self.message_handler: Callable[[int, bytes, bytes], None] | None = None

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
                rtscts=False,
            )
            self.logger.display_log(f"Serial port opened: {self.ser}")
        except serial.SerialException as e:
            self.logger.display_log("Error opening serial port")
            self.logger.display_log(f"Exception: {e}")
            return False
        else:
            return True

    def close(self) -> None:
        """Close serial port."""
        self.stop_event.set()
        if self.read_thread:
            self.read_thread.join()
        if self.ser:
            self.ser.close()
            self.logger.display_log("Serial port closed")

    def send_command(self, hex_data: str) -> None:
        """Send command."""
        if len(hex_data) % 2 != 0:
            self.logger.display_log("Invalid hex data")
            return

        payload = bytes.fromhex(hex_data)
        self.write(payload)

    def write(self, data: bytes) -> None:
        """Calculate the checksum and append it to the payload."""
        if self.ser:
            checksum = calculate_checksum(data)
            payload_with_checksum = data + checksum
            message = cobs.encode(payload_with_checksum) + b"\x00"
            self.ser.write(message)
            self.logger.display_log(f"Published (encoded) `{message}`")
        else:
            self.logger.display_log("Serial port not open")

    def is_open(self) -> bool:
        """Check if connection is open."""
        return self.ser is not None and self.ser.is_open

    def set_message_handler(self, handler: Callable[[int, bytes, bytes], None]) -> None:
        """Set message handler."""
        self.message_handler = handler

    def start_reading(self) -> None:
        """Start reading thread."""
        self.stop_event.clear()
        self.read_thread = threading.Thread(target=self._read_data)
        self.read_thread.start()

    def _read_data(self):
        byte_string: bytes = b""
        self.logger.display_log("Starting read thread...")

        try:
            while not self.stop_event.is_set():
                byte: bytes = self.ser.read(1) if self.ser else b""
                if len(byte) != 0:
                    if byte == b"\x00":
                        decoded_data: bytes = cobs.decode(byte_string)
                        command: int = decoded_data[1] & 0x1F
                        if self.message_handler:
                            self.message_handler(command, decoded_data, byte_string)
                        byte_string = b""
                    else:
                        byte_string += byte

        except serial.SerialException as e:
            self.logger.display_log(f"Exception in read thread: {e}")
            self.logger.display_log("Error reading serial port")
            self.stop_event.set()
            self.close()
