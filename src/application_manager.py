import os
from enum import Enum

from latency_test import LatencyTest
from logger import Logger
from regression_test import RegressionTest
from serial_interface import SerialCommand, SerialInterface


class Mode(Enum):
    """Applocation mode Enum."""

    IDLE = 0
    LATENCY = 1
    COMMAND = 2
    REGRESSION = 3


class ApplicationManager:
    """Application Manager."""

    def __init__(self, port: str, baudrate: int, timeout: float, logger: Logger):
        """Initialize the application manager."""
        self.logger = logger
        self.serial_interface = SerialInterface(port, baudrate, timeout, logger)
        self.latency_test = None
        self.regression_test = None
        self.mode = Mode.IDLE

    def initialize(self) -> bool:
        """Initialize serial interface and open latency test."""
        if not self.serial_interface.open():
            self.logger.display_log("Cannot open serial port. Exiting...")
            return False
        self.serial_interface.set_message_handler(self.handle_message)
        self.serial_interface.start_reading()
        self.latency_test = LatencyTest(self.serial_interface, self.logger)
        self.regression_test = RegressionTest(self.serial_interface, self.logger)
        return True

    def handle_message(
        self,
        command: int,
        decoded_data: bytes,
        byte_string: bytes,
    ) -> None:
        """Handle incoming messages."""
        if self.mode == Mode.LATENCY and self.latency_test:
            self.latency_test.handle_message(command, decoded_data)
        elif self.mode == Mode.COMMAND:
            if command != SerialCommand.ANALOG_COMMAND:
                self.logger.display_log(
                    f"Received raw: {byte_string}, decoded: {decoded_data}",
                )
                self.print_decoded_message(decoded_data)
        elif self.mode == Mode.REGRESSION and self.regression_test:
            self.regression_test.handle_message(command, decoded_data, byte_string)

    def print_decoded_message(self, message: bytes) -> None:
        """Print each byte of the message."""
        logout = ""
        for i, msg in enumerate(message):
            logout += f"{i}: {msg}"

        self.logger.display_log(f"Decoded message: {logout}")
        rxid = message[0]
        rxid <<= 3
        rxid |= (message[1] & 0xE0) >> 5
        command = message[1] & 0x1F
        length = message[2]
        checksum = message[length + 1]
        self.logger.display_log(f"Id: {rxid}, Command: {command}, Checksum: {checksum}")

        if command == SerialCommand.KEY_COMMAND:
            state = message[3] & 0x01
            col = (message[3] >> 4) & 0x0F
            row = (message[3] >> 1) & 0x0F
            self.logger.display_log(
                f"Column: {col}, Row: {row}, State: {state}, Length: {length}",
            )
        elif command == SerialCommand.ANALOG_COMMAND:
            channel = message[3]
            value = message[4] << 8
            value |= message[5]
            self.logger.display_log(f"Channel: {channel}, Value: {value}")

    def run_latency_test(self) -> None:
        """Run latency test."""
        if self.latency_test:
            self.mode = Mode.LATENCY
            self.logger.display_log("Running latency test...")
            self.latency_test.execute_test()
        else:
            self.logger.display_log("Latency test not initialized")

    def run_command_mode(self) -> None:
        """Run command mode."""
        self.mode = Mode.COMMAND
        if self.serial_interface.is_open():
            while True:
                hex_data = input("Enter hex data (x to exit): ")
                if hex_data.lower() == "x":
                    self.logger.display_log("Exiting send command menu...")
                    break
                self.serial_interface.send_command(hex_data)

    def run_regression_test(self) -> None:
        """Run regression test."""
        self.mode = Mode.REGRESSION
        if self.regression_test:
            self.regression_test.execute_test()

    def cleanup(self) -> None:
        """Cleanup resources."""
        self.logger.display_log("Stopping read thread and closing serial port...")
        self.serial_interface.close()

    def display_menu(self) -> None:
        """Display menu."""
        print("\n1. Run latency test")
        print("2. Send command")
        print("3. Regression test")
        print("4. Exit")

    def run(self) -> None:
        """Run the application."""
        try:
            while True:
                os.system("clear")  # noqa: S607, S605
                self.logger.show_log()
                self.display_menu()

                key = input("Enter a choice: ")
                if key == "1":
                    os.system("clear")  # noqa: S605, S607
                    self.run_latency_test()
                elif key == "2":
                    self.run_command_mode()
                elif key == "3":
                    self.run_regression_test()
                elif key == "4":
                    self.logger.display_log("Exiting...")
                    break
                else:
                    self.logger.display_log("Invalid choice\n")
        except Exception as e:  # noqa: BLE001
            self.logger.display_log(f"Exception in main loop: {e}")
        finally:
            self.cleanup()
