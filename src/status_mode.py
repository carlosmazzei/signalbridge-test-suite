"""Status mode module."""

import datetime
import logging
import time
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from tabulate import tabulate

from serial_interface import SerialCommand, SerialInterface

logger = logging.getLogger(__name__)

ERROR_HEADER_BYTES = bytes([0x00, 0x37])
TASK_HEADER_BYTES = bytes([0x00, 0x38])


@dataclass
class ErrorItem:
    """Represents an error item."""

    message: str
    value: int = 0
    last_updated: float = 0


@dataclass
class TaskItem:
    """Represents a task item."""

    name: str
    index: int = 0
    absoulute_time = 0
    percent_time = 0
    high_watermark = 0
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
        COBS_DECODE_ERROR = 7
        RECEIVE_BUFFER_OVERFLOW_ERROR = 8
        CHECKSUM_ERROR = 9
        BUFFER_OVERFLOW_ERROR = 10
        UNKNOWN_CMD_ERROR = 11

    class TaskNames(StrEnum):
        """Definition of tasks."""

        IDLE_TASK_NAME = "Idle"
        CDC_TASK_NAME = "CDC"
        UART_TASK_NAME = "UART handling"
        DECODE_TASK_NAME = "Decode reception"
        PROCESS_TASK_NAME = "Inbound process"
        ADC_TASK_NAME = "ADC read"
        KEY_TASK_NAME = "Key read"
        ENCODER_TASK_NAME = "Encoder read"

    class TaskIndex(IntEnum):
        """Definitions of task indexes."""

        CDC_TASK_INDEX = 0
        UART_EVENT_TASK_INDEX = 1
        DECODE_RECEPTION_TASK_INDEX = 2
        PROCESS_OUTBOUND_TASK_INDEX = 3
        ADC_READ_TASK_INDEX = 4
        KEYPAD_TASK_INDEX = 5
        ENCODER_READ_TASK_INDEX = 6
        IDLE_TASK_INDEX = 7

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
            self.ErrorCodes.COBS_DECODE_ERROR: ErrorItem("Cobs Decode Error"),
            self.ErrorCodes.RECEIVE_BUFFER_OVERFLOW_ERROR: ErrorItem(
                "Receive Buffer Overflow"
            ),
            self.ErrorCodes.CHECKSUM_ERROR: ErrorItem("Checksum Error"),
            self.ErrorCodes.BUFFER_OVERFLOW_ERROR: ErrorItem("Buffer Overflow Error"),
            self.ErrorCodes.UNKNOWN_CMD_ERROR: ErrorItem("Unknown Command Error"),
        }

        self.task_items: dict[int, TaskItem] = {
            self.TaskIndex.IDLE_TASK_INDEX: TaskItem(
                name=self.TaskNames.IDLE_TASK_NAME
            ),
            self.TaskIndex.CDC_TASK_INDEX: TaskItem(name=self.TaskNames.CDC_TASK_NAME),
            self.TaskIndex.UART_EVENT_TASK_INDEX: TaskItem(
                name=self.TaskNames.UART_TASK_NAME
            ),
            self.TaskIndex.DECODE_RECEPTION_TASK_INDEX: TaskItem(
                name=self.TaskNames.DECODE_TASK_NAME
            ),
            self.TaskIndex.PROCESS_OUTBOUND_TASK_INDEX: TaskItem(
                name=self.TaskNames.PROCESS_TASK_NAME
            ),
            self.TaskIndex.ADC_READ_TASK_INDEX: TaskItem(
                name=self.TaskNames.ADC_TASK_NAME
            ),
            self.TaskIndex.KEYPAD_TASK_INDEX: TaskItem(
                name=self.TaskNames.KEY_TASK_NAME
            ),
            self.TaskIndex.ENCODER_READ_TASK_INDEX: TaskItem(
                name=self.TaskNames.ENCODER_TASK_NAME
            ),
        }

    def handle_message(self, command: int, decoded_data: bytes) -> None:
        """Handle incoming messages."""
        try:
            if command == SerialCommand.ERROR_STATUS_COMMAND.value:
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
            elif command == SerialCommand.TASK_STATUS_COMMAND.value:
                status_index = decoded_data[3]
                abs_time_bytes = [
                    decoded_data[4],
                    decoded_data[5],
                    decoded_data[6],
                    decoded_data[7],
                ]
                abs_time = int.from_bytes(abs_time_bytes, byteorder="big")

                perc_time_bytes = [
                    decoded_data[8],
                    decoded_data[9],
                    decoded_data[10],
                    decoded_data[11],
                ]
                perc_time = int.from_bytes(perc_time_bytes, byteorder="big")

                hwatermark_bytes = [
                    decoded_data[12],
                    decoded_data[13],
                    decoded_data[14],
                    decoded_data[15],
                ]
                h_watermark = int.from_bytes(hwatermark_bytes, byteorder="big")

                if status_index in self.task_items:
                    task_item = self.task_items[status_index]
                    task_item.absoulute_time = abs_time
                    task_item.percent_time = perc_time
                    task_item.high_watermark = h_watermark
                    task_item.last_updated = time.time()
                    self.logger.info("[%s] updated", task_item.name)

        except IndexError:
            self.logger.exception("Error parsing status command")

    def _status_update(self, header: bytes, index: int) -> None:
        """Send status update command."""
        payload = header + bytes([0x01]) + index.to_bytes(1, byteorder="big")
        self.logger.info("Sending status update command for [%s])", index)
        self.ser.write(payload)

    def _update_error_status(self) -> None:
        """Send update status request for error items."""
        self.logger.info("Requesting for status ...")
        for index in self.error_items:
            self._status_update(ERROR_HEADER_BYTES, index)
            time.sleep(0.1)
            self.logger.info(
                "[%s] status update requested", self.error_items[index].message
            )

        self.logger.info("Status request complete")

    def _update_task_status(self) -> None:
        """Send status request for task stats."""
        for index in self.task_items:
            self._status_update(TASK_HEADER_BYTES, index)
            time.sleep(0.1)
            self.logger.info(
                "[%s] status update requested", self.task_items[index].name
            )

        self.logger.info("Status request complete")

    def _display_error_status(self) -> None:
        """Display error status."""
        print("\nError Status:")
        error_data = []
        for index in self.error_items:
            item = self.error_items[index]
            last_updated = "N/A"
            if item.last_updated != 0:
                last_updated = datetime.datetime.fromtimestamp(
                    item.last_updated,
                    tz=datetime.UTC,
                ).strftime("%Y-%m-%d %H:%M:%S")
            error_data.append([item.message, item.value, last_updated])

        print(
            tabulate(
                error_data,
                headers=["Error", "Value", "Last Updated"],
                tablefmt="simple_grid",
            )
        )

    def format_time_from_microseconds(self, microseconds: int) -> str:
        """Format time from microseconds."""
        milliseconds = microseconds / 1000
        seconds, ms = divmod(milliseconds, 1000)
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes):02}:{int(seconds):02}:{int(ms):03}"

    def _display_task_status(self) -> None:
        """Display task status."""
        print("\nTask Status:")
        task_data = []
        for index in self.task_items:
            item = self.task_items[index]
            last_updated = "N/A"
            if item.last_updated != 0:
                last_updated = datetime.datetime.fromtimestamp(
                    item.last_updated,
                    tz=datetime.UTC,
                ).strftime("%Y-%m-%d %H:%M:%S")
            formatted_time = self.format_time_from_microseconds(item.absoulute_time)
            task_data.append(
                [
                    item.name,
                    formatted_time,
                    f"{item.percent_time}%",
                    item.high_watermark,
                    last_updated,
                ]
            )

        print(
            tabulate(
                task_data,
                headers=[
                    "Task",
                    "Absolute Time (mm:ss:ms)",
                    "% Time",
                    "High Watermark",
                    "Last Updated",
                ],
                tablefmt="simple_grid",
            )
        )

        core0_total_time = (
            self.task_items[self.TaskIndex.CDC_TASK_INDEX].absoulute_time
            + self.task_items[self.TaskIndex.UART_EVENT_TASK_INDEX].absoulute_time
        )
        print(f"\nCore 0 total time: {core0_total_time:,.3f}")

        core1_total_time = (
            self.task_items[self.TaskIndex.IDLE_TASK_INDEX].absoulute_time
            + self.task_items[self.TaskIndex.ENCODER_READ_TASK_INDEX].absoulute_time
            + self.task_items[self.TaskIndex.ADC_READ_TASK_INDEX].absoulute_time
            + self.task_items[self.TaskIndex.KEYPAD_TASK_INDEX].absoulute_time
            + self.task_items[self.TaskIndex.PROCESS_OUTBOUND_TASK_INDEX].absoulute_time
            + self.task_items[self.TaskIndex.DECODE_RECEPTION_TASK_INDEX].absoulute_time
        )
        print(f"Core 1 total time: {core1_total_time:,.3f}")

    def _handle_user_choice(self, choice: str) -> bool:
        """Handle user choice and return whether to continue."""
        if choice == "1":
            self._update_error_status()
        elif choice == "2":
            self._update_task_status()
        elif choice == "3":
            return True
        elif choice == "4":
            return False
        else:
            print("Invalid choice, please try again.")
        return True

    def execute_test(self) -> None:
        """Execute status mode test."""
        while True:
            self._display_error_status()
            self._display_task_status()

            print("\nSelect an option:")
            print("1. Request error status")
            print("2. Request task status")
            print("3. Show status")
            print("4. Exit")

            choice = input("Enter choice (1, 2, 3 or 4): ")

            if not self._handle_user_choice(choice):
                return
