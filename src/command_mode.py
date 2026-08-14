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

"""Command mode module for handling command operations."""

import logging
import queue
import sys
import threading

from cobs import cobs
from rich.panel import Panel

from checksum import calculate_checksum
from logger_config import setup_logging
from serial_interface import SerialCommand, SerialInterface
from ui_console import console

setup_logging()

logger = logging.getLogger(__name__)

# Minimum decoded lengths before the corresponding fields can be indexed.
_HEADER_LEN = 3  # rxID_high, rxID_low|cmd, len_field
_KEY_FRAME_LEN = 4  # header + packed col/row/state byte
_ANALOG_FRAME_LEN = 6  # header + channel + 2 value bytes

# Bound on undisplayed frames, so a stalled display cannot grow without limit.
MAX_QUEUE_SIZE = 10000


class CommandMode:
    """
    CommandMode class for handling command operations.

    This class encapsulates the functionality for sending commands
    and processing received messages in command mode.
    """

    def __init__(self, serial_interface: SerialInterface) -> None:
        """
        Initialize the CommandMode.

        Args:
        ----
        serial_interface (SerialInterface): The serial interface to use.
        logger (Logger): The logger instance to use.

        """
        self.serial_interface = serial_interface
        self.message_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        self.running = False
        self.input_lock = threading.Lock()
        self.current_input = ""
        self.prompt = "\nEnter hex data (x to exit): "

    def execute_command_mode(self) -> None:
        """Execute the command mode loop."""
        if self.serial_interface.is_open():
            console.print(
                Panel(
                    "[dim]Type hex data to send. Enter [bold]x[/bold] to exit.[/dim]",
                    title="Command Mode",
                    title_align="left",
                )
            )
            self.running = True
            message_thread = threading.Thread(target=self._process_messages)
            message_thread.start()

            try:
                while self.running:
                    self._print_prompt()
                    hex_data = self._get_input()
                    if hex_data.lower() == "x":
                        logger.info("Exiting send command menu...")
                        self.running = False
                        break
                    self.serial_interface.send_command(hex_data)
            except KeyboardInterrupt:
                self.running = False

            message_thread.join()
        else:
            console.print(
                Panel(
                    "[yellow]Serial interface is not connected.[/yellow]",
                    title="Command Mode",
                    title_align="left",
                )
            )

    def _print_prompt(self) -> None:
        """Print the input prompt."""
        with self.input_lock:
            sys.stdout.write(self.prompt)
            sys.stdout.flush()

    def _get_input(self) -> str:
        """Get input from the user."""
        self.current_input = ""
        while self.running:
            char = sys.stdin.read(1)
            with self.input_lock:
                if char == "\n":
                    return self.current_input

                if char == "\x7f":  # Handle backspace
                    if self.current_input:
                        self.current_input = self.current_input[:-1]
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                else:
                    self.current_input += char
                    sys.stdout.write(char)
                    sys.stdout.flush()
        return ""

    def _process_messages(self) -> None:
        """Process incoming messages from the queue."""
        while self.running:
            try:
                message = self.message_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._handle_message(*message)
            except Exception:  # A bad frame must not kill the display thread
                logger.exception("Error displaying received message")

    def handle_message(
        self,
        command: int,
        decoded_data: bytes,
        byte_string: bytes,
    ) -> None:
        """
        Handle incoming messages in command mode.

        Args:
        ----
        command (int): The command received.
        decoded_data (bytes): The decoded data received.
        byte_string (bytes): The raw byte string received.

        """
        # Add message to queue for processing.  Called from the serial
        # processing thread, so never block it on a saturated queue.
        try:
            self.message_queue.put_nowait((command, decoded_data, byte_string))
        except queue.Full:
            logger.warning("Command mode queue full; dropping frame for display")

    def _handle_message(
        self,
        command: int,
        decoded_data: bytes,
        byte_string: bytes,
    ) -> None:
        """Handle messages from the queue."""
        # Filter analog command to not clutter the output
        if command != SerialCommand.ANALOG_COMMAND.value:
            with self.input_lock:
                # Clear the current line
                sys.stdout.write(
                    "\r" + " " * (len(self.prompt) + len(self.current_input)) + "\r",
                )
                sys.stdout.flush()

                # Print the message
                try:
                    cobs_decoded = cobs.decode(byte_string)
                except cobs.DecodeError:
                    logger.warning("Undecodable frame: %s", byte_string.hex())
                    cobs_decoded = b""
                received_checksum = cobs_decoded[-1:]
                calculated_checksum = calculate_checksum(cobs_decoded[:-1])
                logger.info(
                    "Received raw: %s, decoded: %s, Received Checksum: %s, "
                    "Calculated Checksum: %s, Match: %s",
                    byte_string,
                    decoded_data,
                    received_checksum,
                    calculated_checksum,
                    received_checksum == calculated_checksum,
                )
                self._print_decoded_message(decoded_data)

                # Reprint the prompt and current input
                sys.stdout.write(self.prompt + self.current_input)
                sys.stdout.flush()

    def _print_decoded_message(self, message: bytes) -> None:
        """
        Print each byte of the message and additional decoded information.

        Args:
        ----
        message (bytes): The message to decode and print.

        """
        logout = " ".join(f"{i}: {msg}" for i, msg in enumerate(message))
        logger.info("Decoded message: %s", logout)
        if len(message) < _HEADER_LEN:
            logger.warning("Frame too short to decode header (%d bytes)", len(message))
            return
        rxid = (message[0] << 3) | ((message[1] & 0xE0) >> 5)
        command = message[1] & 0x1F
        length = message[2]
        logger.info("Id: %s, Command: %s", rxid, command)
        if command == SerialCommand.KEY_COMMAND.value:
            if len(message) < _KEY_FRAME_LEN:
                logger.warning("Key frame truncated (%d bytes)", len(message))
                return
            state = message[3] & 0x01
            col = (message[3] >> 4) & 0x0F
            row = (message[3] >> 1) & 0x0F
            logger.info(
                "Column: %s, Row: %s, State: %s, Length: %s",
                col,
                row,
                state,
                length,
            )
        elif command == SerialCommand.ANALOG_COMMAND.value:
            if len(message) < _ANALOG_FRAME_LEN:
                logger.warning("Analog frame truncated (%d bytes)", len(message))
                return
            channel = message[3]
            value = (message[4] << 8) | message[5]
            logger.info("Channel: %s, Value: %s", channel, value)
