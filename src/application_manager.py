import os
from enum import Enum
from typing import TYPE_CHECKING

from latency_test import LatencyTest
from logger import Logger
from serial_interface import SerialCommand, SerialInterface
from visualize_results import VisualizeResults

if TYPE_CHECKING:
    from regression_test import RegressionTest


class Mode(Enum):
    """Applocation mode Enum."""

    IDLE = 0
    LATENCY = 1
    COMMAND = 2
    REGRESSION = 3
    VISUALIZE = 4


class ApplicationManager:
    """Application Manager."""

    def __init__(self, port: str, baudrate: int, timeout: float, logger: Logger):
        """Initialize the application manager."""
        self.logger: Logger = logger
        self.serial_interface: SerialInterface = SerialInterface(
            port,
            baudrate,
            timeout,
            logger,
        )
        self.latency_test: LatencyTest | None = None
        self.regression_test: RegressionTest | None = None
        self.mode: Mode = Mode.IDLE
        self.available_modes = {Mode.VISUALIZE}

    def initialize(self) -> bool:
        """Initialize serial interface."""
        self.visualize_results = VisualizeResults(self.logger)
        if self.serial_interface.open():
            self.serial_interface.set_message_handler(self.handle_message)
            self.serial_interface.start_reading()
            self.latency_test = LatencyTest(self.serial_interface, self.logger)
            self.available_modes.update([Mode.LATENCY, Mode.COMMAND, Mode.REGRESSION])
            self.logger.display_log("Serial interface opened successfully.")
        else:
            self.logger.display_log(
                "Failed to open serial interface. Some features will be disabled.",
            )
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
            # Filter analog command to not clutter the output
            if command != SerialCommand.ANALOG_COMMAND.value:
                print(
                    f"Received raw: {byte_string}, decoded: {decoded_data}",
                )
                self.print_decoded_message(decoded_data)
        elif self.mode == Mode.REGRESSION and self.regression_test:
            self.regression_test.handle_message(command, decoded_data, byte_string)

    def print_decoded_message(self, message: bytes) -> None:
        """Print each byte of the message."""
        logout = ""
        for i, msg in enumerate(message):
            logout += f"{i}: {msg} | "

        print(f"Decoded message: {logout}")
        rxid = message[0]
        rxid <<= 3
        rxid |= (message[1] & 0xE0) >> 5
        command = message[1] & 0x1F
        length = message[2]
        checksum = message[length + 1]
        print(f"Id: {rxid}, Command: {command}, Checksum: {checksum}")

        if command == SerialCommand.KEY_COMMAND.value:
            state = message[3] & 0x01
            col = (message[3] >> 4) & 0x0F
            row = (message[3] >> 1) & 0x0F
            print(
                f"Column: {col}, Row: {row}, State: {state}, Length: {length}",
            )
        elif command == SerialCommand.ANALOG_COMMAND.value:
            channel = message[3]
            value = message[4] << 8
            value |= message[5]
            print(f"Channel: {channel}, Value: {value}")

    def run_latency_test(self) -> None:
        """Run latency test."""
        if Mode.LATENCY in self.available_modes:
            self.mode = Mode.LATENCY
            self.logger.display_log("Running latency test...")
            if self.latency_test:
                self.latency_test.execute_test()
        else:
            self.logger.display_log("Latency test not initialized")

    def run_command_mode(self) -> None:
        """Run command mode."""
        if Mode.COMMAND in self.available_modes:
            self.mode = Mode.COMMAND
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

    def run_regression_test(self) -> None:
        """Run regression test."""
        if Mode.REGRESSION in self.available_modes:
            self.mode = Mode.REGRESSION
            if self.regression_test:
                self.regression_test.execute_test()
        else:
            self.logger.display_log(
                "Regression test is not available. Serial interface is not connected.",
            )

    def run_visualization(self) -> None:
        """Run visualization."""
        self.mode = Mode.VISUALIZE
        self.visualize_results.execute_visualization()

    def cleanup(self) -> None:
        """Cleanup resources."""
        self.logger.display_log("Stopping read thread and closing serial port...")
        self.serial_interface.close()

    def display_menu(self) -> None:
        """Display the menu."""
        print("\nAvailable options:")
        if Mode.LATENCY in self.available_modes:
            print("1. Run latency test")
        if Mode.COMMAND in self.available_modes:
            print("2. Send command")
        if Mode.REGRESSION in self.available_modes:
            print("3. Regression test")
        print("4. Visualize test results")
        print("5. Exit")

    def run(self) -> None:
        """Run the application."""
        try:
            while True:
                os.system("clear")  # noqa: S605, S607
                self.logger.show_log()
                self.display_menu()

                key = input("Enter a choice: ")
                if key == "1" and Mode.LATENCY in self.available_modes:
                    os.system("clear")  # noqa: S605, S607
                    self.run_latency_test()
                elif key == "2" and Mode.COMMAND in self.available_modes:
                    self.run_command_mode()
                elif key == "3" and Mode.REGRESSION in self.available_modes:
                    self.run_regression_test()
                elif key == "4" and Mode.VISUALIZE in self.available_modes:
                    self.run_visualization()
                elif key == "5":
                    self.logger.display_log("Exiting...")
                    break
                else:
                    self.logger.display_log("Invalid choice or option not available\n")
        except Exception as e:  # noqa: BLE001
            self.logger.display_log(f"Exception in main loop: {e}")
            self.logger.show_log()
        finally:
            self.cleanup()
