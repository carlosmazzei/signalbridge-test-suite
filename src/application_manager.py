"""Application Manager module."""

import logging
import os
from enum import Enum
from typing import TYPE_CHECKING

from command_mode import CommandMode  # New import for refactored command mode
from latency_test import LatencyTest
from logger_config import setup_logging
from serial_interface import SerialInterface
from visualize_results import VisualizeResults

if TYPE_CHECKING:
    from regression_test import RegressionTest

setup_logging()

logger = logging.getLogger(__name__)


class Mode(Enum):
    """Application mode Enum."""

    IDLE = 0
    LATENCY = 1
    COMMAND = 2
    REGRESSION = 3
    VISUALIZE = 4


class ApplicationManager:
    """
    Application Manager class.

    This class manages the overall application flow, including initialization,
    mode switching, and cleanup.
    """

    def __init__(self, port: str, baudrate: int, timeout: float) -> None:
        """
        Initialize the application manager.

        Args:
        ----
            port (str): The serial port to use.
            baudrate (int): The baud rate for serial communication.
            timeout (float): The timeout for serial communication.
            logger (Logger): The logger instance to use.

        """
        self.serial_interface: SerialInterface = SerialInterface(
            port,
            baudrate,
            timeout,
        )
        self.latency_test: LatencyTest | None = None
        self.regression_test: RegressionTest | None = None
        self.command_mode: CommandMode | None = None  # New attribute for command mode
        self.mode: Mode = Mode.IDLE
        self.available_modes = {Mode.VISUALIZE}
        self.visualize_results: VisualizeResults | None = None

    def initialize(self) -> bool:
        """
        Initialize serial interface and set up components.

        Returns
        -------
            bool: True if initialization was successful, False otherwise.

        """
        self.visualize_results = VisualizeResults()
        if self.serial_interface.open():
            self.serial_interface.set_message_handler(self.handle_message)
            self.serial_interface.start_reading()
            self.latency_test = LatencyTest(self.serial_interface)
            self.command_mode = CommandMode(self.serial_interface)
            self.available_modes.update([Mode.LATENCY, Mode.COMMAND, Mode.REGRESSION])
            logger.info("Serial interface opened successfully.")
        else:
            logger.error(
                "Failed to open serial interface. Some features will be disabled.",
            )
            return False
        return True

    def handle_message(
        self,
        command: int,
        decoded_data: bytes,
        byte_string: bytes,
    ) -> None:
        """
        Handle incoming messages based on the current mode.

        Args:
        ----
            command (int): The command received.
            decoded_data (bytes): The decoded data received.
            byte_string (bytes): The raw byte string received.

        """
        if self.mode == Mode.LATENCY and self.latency_test:
            self.latency_test.handle_message(command, decoded_data)
        elif self.mode == Mode.COMMAND and self.command_mode:
            self.command_mode.handle_message(command, decoded_data, byte_string)
        elif self.mode == Mode.REGRESSION and self.regression_test:
            self.regression_test.handle_message(command, decoded_data, byte_string)

    def run_latency_test(self) -> None:
        """Run latency test if available."""
        if Mode.LATENCY in self.available_modes and self.latency_test:
            self.mode = Mode.LATENCY
            logger.info("Running latency test...")
            self.latency_test.execute_test()
        else:
            logger.info("Latency test not initialized")

    def run_command_mode(self) -> None:
        """Run command mode if available."""
        if Mode.COMMAND in self.available_modes and self.command_mode:
            self.mode = Mode.COMMAND
            self.command_mode.execute_command_mode()
        else:
            logger.info(
                "Command mode is not available. Serial interface is not connected.",
            )

    def run_regression_test(self) -> None:
        """Run regression test if available."""
        if Mode.REGRESSION in self.available_modes and self.regression_test:
            self.mode = Mode.REGRESSION
            self.regression_test.execute_test()
        else:
            logger.info(
                "Regression test is not available. Serial interface is not connected.",
            )

    def run_visualization(self) -> None:
        """Run visualization if available."""
        if self.visualize_results:
            self.mode = Mode.VISUALIZE
            self.visualize_results.execute_visualization()
        else:
            logger.info("Visualization is not initialized.")

    def cleanup(self) -> None:
        """Cleanup resources and close serial interface."""
        logger.info("Stopping read thread and closing serial port...")
        self.serial_interface.close()

    def display_menu(self) -> None:
        """Display the menu of available options."""
        print("\nAvailable options:")
        if Mode.LATENCY in self.available_modes:
            print("1. Run latency test")
        if Mode.COMMAND in self.available_modes:
            print("2. Send command")
        if Mode.REGRESSION in self.available_modes:
            print("3. Regression test")
        if Mode.VISUALIZE in self.available_modes:
            print("4. Visualize test results")
        print("5. Exit")

    def run(self) -> None:
        """
        Run the main application loop.

        This method displays the menu, handles user input, and executes
        the chosen option until the user decides to exit.
        """
        try:
            while True:
                self.display_menu()

                choice = input("Enter a choice: ")
                if choice == "1" and Mode.LATENCY in self.available_modes:
                    os.system("clear")  # noqa: S605, S607
                    self.run_latency_test()
                elif choice == "2" and Mode.COMMAND in self.available_modes:
                    self.run_command_mode()
                elif choice == "3" and Mode.REGRESSION in self.available_modes:
                    self.run_regression_test()
                elif choice == "4" and Mode.VISUALIZE in self.available_modes:
                    self.run_visualization()
                elif choice == "5":
                    logger.info("Exiting...")
                    break
                else:
                    logger.info("Invalid choice or option not available\n")
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received, exiting gracefully.")
        except Exception:
            logger.exception("Exception in main loop.")
            raise
        finally:
            self.cleanup()
