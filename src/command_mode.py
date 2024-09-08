from checksum import calculate_checksum
from cobs import cobs
from logger import Logger
from serial_interface import SerialCommand, SerialInterface


class CommandMode:
    """CommandMode class for handling command operations.

    This class encapsulates the functionality for sending commands
    and processing received messages in command mode.
    """

    def __init__(self, serial_interface: SerialInterface, logger: Logger):
        """Initialize the CommandMode.

        Args:
        ----
            serial_interface (SerialInterface): The serial interface to use.
            logger (Logger): The logger instance to use.

        """
        self.serial_interface = serial_interface
        self.logger = logger

    def execute_command_mode(self) -> None:
        """Execute the command mode loop."""
        if self.serial_interface.is_open():
            while True:
                hex_data = input("Enter hex data (x to exit): ")
                if hex_data.lower() == "x":
                    self.logger.display_log("Exiting send command menu...")
                    break
                self.serial_interface.send_command(hex_data)
        else:
            self.logger.display_log(
                "Command mode is not available. Serial interface is not connected.",
            )

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
        # Filter analog command to not clutter the output
        if command != SerialCommand.ANALOG_COMMAND.value:

            cobs_decoded = cobs.decode(byte_string)
            received_checksum = cobs_decoded[-1:]
            calculated_checksum = calculate_checksum(cobs_decoded[:-1])

            print(
                f"Received raw: {byte_string}, decoded: {decoded_data}, , Received Checksum: {received_checksum}, Calculated Checksum: {calculated_checksum}",
            )
            self._print_decoded_message(decoded_data)

    def _print_decoded_message(self, message: bytes) -> None:
        """Print each byte of the message and additional decoded information.

        Args:
        ----
            message (bytes): The message to decode and print.

        """
        logout = " ".join(f"{i}: {msg}" for i, msg in enumerate(message))
        print(f"Decoded message: {logout}")

        rxid = (message[0] << 3) | ((message[1] & 0xE0) >> 5)
        command = message[1] & 0x1F
        length = message[2]

        print(f"Id: {rxid}, Command: {command}")

        if command == SerialCommand.KEY_COMMAND.value:
            state = message[3] & 0x01
            col = (message[3] >> 4) & 0x0F
            row = (message[3] >> 1) & 0x0F
            print(f"Column: {col}, Row: {row}, State: {state}, Length: {length}")
        elif command == SerialCommand.ANALOG_COMMAND.value:
            channel = message[3]
            value = (message[4] << 8) | message[5]
            print(f"Channel: {channel}, Value: {value}")
