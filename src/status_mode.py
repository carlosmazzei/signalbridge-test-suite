"""Status mode module."""

import logging
import time
from dataclasses import dataclass
from enum import IntEnum

from serial_interface import SerialCommand, SerialInterface

logger = logging.getLogger(__name__)

HEADER_BYTES = bytes([0x00, 0x37])


@dataclass
class ErrorItem:
    """Represents an error item."""

    message: str
    value: int = 0
    last_updated: float = 0


class StatusMode:
    """Status mode class."""

    class ErrorCodes(IntEnum):
        """Error codes for status mode."""

        QUEUE_SEND_ERROR = 1
        QUEUE_RECEIVE_ERROR = 2
        DISPLAY_OUT_ERROR = 3
        LED_OUT_ERROR = 4
        WATCHDOG_ERROR = 5
        MSG_MALFORMED_ERROR = 6
        RECEIVE_BUFFER_OVERFLOW_ERROR = 7
        CHECKSUM_ERROR = 8
        BUFFER_OVERFLOW_ERROR = 9
        UNKNOWN_CMD_ERROR = 10

    def __init__(self, ser: SerialInterface) -> None:
        """Initialize status mode class."""
        self.logger = logger
        self.ser = ser
        self.error_items: dict[int, ErrorItem] = {
            self.ErrorCodes.QUEUE_SEND_ERROR: ErrorItem("Queue Send Error"),
            self.ErrorCodes.QUEUE_RECEIVE_ERROR: ErrorItem("Queue Receive Error"),
            self.ErrorCodes.DISPLAY_OUT_ERROR: ErrorItem("Display Output Error"),
            self.ErrorCodes.LED_OUT_ERROR: ErrorItem("LED Output Error"),
            self.ErrorCodes.WATCHDOG_ERROR: ErrorItem("Watchdog Error"),
            self.ErrorCodes.MSG_MALFORMED_ERROR: ErrorItem("Malformed Message Error"),
            self.ErrorCodes.RECEIVE_BUFFER_OVERFLOW_ERROR: ErrorItem(
                "Receive Buffer Overflow"
            ),
            self.ErrorCodes.CHECKSUM_ERROR: ErrorItem("Checksum Error"),
            self.ErrorCodes.BUFFER_OVERFLOW_ERROR: ErrorItem("Buffer Overflow Error"),
            self.ErrorCodes.UNKNOWN_CMD_ERROR: ErrorItem("Unknown Command Error"),
        }

    def handle_message(self, command: int, decoded_data: bytes) -> None:
        """Handle incoming messages."""
        if command == SerialCommand.STATUS_COMMAND.value:
            try:
                status_index = decoded_data[3]
                status_value_bytes = [decoded_data[4], decoded_data[5]]
                status_value = int.from_bytes(status_value_bytes, byteorder="big")

                # Update the corresponding error item
                if status_index in self.error_items:
                    error_item = self.error_items[status_index]
                    error_item.value = status_value
                    error_item.last_updated = time.time()
                    self.logger.info(
                        "%s value updated to %d", error_item.message, error_item.value
                    )
            except IndexError:
                self.logger.exception("Error parsing status command")

    def _status_update(self, index: int) -> None:
        """Send status update command."""
        payload = HEADER_BYTES + bytes([0x01]) + index.to_bytes(1, byteorder="big")
        self.logger.info(
            "Sending status update command for [%s])", self.error_items[index].message
        )
        self.ser.write(payload)

    def update(self) -> None:
        """Send update status request for error items."""
        self.logger.info("Requesting for status ...")
        for index in self.error_items:
            self._status_update(index)
            time.sleep(0.1)
            self.logger.info(
                "[%s] status update requested", self.error_items[index].message
            )

        self.logger.info("Status request complete")

    def execute_test(self) -> None:
        """Execute status mode test."""
        while True:
            print("Current status:")
            for index in self.error_items:
                # format last updated to time
                if self.error_items[index].last_updated != 0:
                    last_updated = format(
                        self.error_items[index].last_updated, "%Y-%m-%d %H:%M:%S"
                    )
                print(
                    f"{self.error_items[index].message}: "
                    f"{self.error_items[index].value} "
                    f"(last updated {last_updated})"
                )

            print("\nSelect an option:")
            print("1. Request update status")
            print("2. Refresh status")
            print("3. Exit")

            choice = input("Enter choice (1, 2 or 3): ")

            if choice == "1":
                self.update()
            elif choice == "2":
                continue
            elif choice == "3":
                return
            else:
                print("Invalid choice, please try again.")
                continue
