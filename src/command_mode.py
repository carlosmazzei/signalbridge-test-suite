import logging
import queue
import sys
import threading

from checksum import calculate_checksum
from cobs import cobs
from serial_interface import SerialCommand, SerialInterface

# Set up logger
logger = logging.getLogger("CommandMode")
logger.setLevel(logging.INFO)

# Create console handler and set level to INFO
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Add formatter to ch
ch.setFormatter(formatter)

# Add ch to logger
logger.addHandler(ch)


class CommandMode:
    """CommandMode class for handling command operations.

    This class encapsulates the functionality for sending commands
    and processing received messages in command mode.
    """

    def __init__(self, serial_interface: SerialInterface):
        """Initialize the CommandMode.

        Args:
        ----
        serial_interface (SerialInterface): The serial interface to use.
        logger (Logger): The logger instance to use.

        """
        self.serial_interface = serial_interface
        self.logger = logger
        self.message_queue = queue.Queue()
        self.running = False
        self.input_lock = threading.Lock()
        self.current_input = ""
        self.prompt = "\nEnter hex data (x to exit): "

    def execute_command_mode(self) -> None:
        """Execute the command mode loop."""
        if self.serial_interface.is_open():
            self.running = True
            message_thread = threading.Thread(target=self._process_messages)
            message_thread.start()

            try:
                while self.running:
                    self._print_prompt()
                    hex_data = self._get_input()
                    if hex_data.lower() == "x":
                        self.logger.info("Exiting send command menu...")
                        self.running = False
                        break
                    self.serial_interface.send_command(hex_data)
            except KeyboardInterrupt:
                self.running = False

            message_thread.join()
        else:
            self.logger.info(
                "Command mode is not available. Serial interface is not connected.",
            )

    def _print_prompt(self):
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

    def _process_messages(self):
        """Process incoming messages from the queue."""
        while self.running:
            try:
                message = self.message_queue.get(timeout=0.1)
                self._handle_message(*message)
            except queue.Empty:
                continue

    def handle_message(
        self,
        command: int,
        decoded_data: bytes,
        byte_string: bytes,
    ) -> None:
        """Handle incoming messages in command mode.

        Args:
        ----
        command (int): The command received.
        decoded_data (bytes): The decoded data received.
        byte_string (bytes): The raw byte string received.

        """
        # Add message to queue for processing
        self.message_queue.put((command, decoded_data, byte_string))

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
                cobs_decoded = cobs.decode(byte_string)
                received_checksum = cobs_decoded[-1:]
                calculated_checksum = calculate_checksum(cobs_decoded[:-1])
                self.logger.info(
                    f"Received raw: {byte_string}, decoded: {decoded_data}, Received Checksum: {received_checksum}, Calculated Checksum: {calculated_checksum}",  # noqa: G004
                )
                self._print_decoded_message(decoded_data)

                # Reprint the prompt and current input
                sys.stdout.write(self.prompt + self.current_input)
                sys.stdout.flush()

    def _print_decoded_message(self, message: bytes) -> None:
        """Print each byte of the message and additional decoded information.

        Args:
        ----
        message (bytes): The message to decode and print.

        """
        logout = " ".join(f"{i}: {msg}" for i, msg in enumerate(message))
        self.logger.info(f"Decoded message: {logout}")  # noqa: G004
        rxid = (message[0] << 3) | ((message[1] & 0xE0) >> 5)
        command = message[1] & 0x1F
        length = message[2]
        self.logger.info(f"Id: {rxid}, Command: {command}")  # noqa: G004
        if command == SerialCommand.KEY_COMMAND.value:
            state = message[3] & 0x01
            col = (message[3] >> 4) & 0x0F
            row = (message[3] >> 1) & 0x0F
            self.logger.info(
                f"Column: {col}, Row: {row}, State: {state}, Length: {length}",  # noqa: G004
            )
        elif command == SerialCommand.ANALOG_COMMAND.value:
            channel = message[3]
            value = (message[4] << 8) | message[5]
            self.logger.info(f"Channel: {channel}, Value: {value}")  # noqa: G004
