"""Status mode module."""

import datetime
import logging
import time
from dataclasses import dataclass

from tabulate import tabulate

from base_test import (
    STATISTICS_DISPLAY_NAMES,
    STATISTICS_HEADER_BYTES,
    STATISTICS_ITEMS,
    TASK_DISPLAY_NAMES,
    TASK_HEADER_BYTES,
    TASK_ITEMS,
)
from serial_interface import SerialCommand, SerialInterface

logger = logging.getLogger(__name__)

# Reverse lookup: name -> index for TASK_ITEMS
_TASK_INDEX_BY_NAME = {name: idx for idx, name in TASK_ITEMS.items()}


@dataclass
class StatisticsItem:
    """Represents an statistics item."""

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

    def __init__(self, ser: SerialInterface) -> None:
        """Initialize status mode class."""
        self.logger = logger
        self.ser = ser
        self.error_items: dict[int, StatisticsItem] = {
            idx: StatisticsItem(STATISTICS_DISPLAY_NAMES[name])
            for idx, name in STATISTICS_ITEMS.items()
        }
        self.task_items: dict[int, TaskItem] = {
            idx: TaskItem(name=TASK_DISPLAY_NAMES[name])
            for idx, name in TASK_ITEMS.items()
        }

    def handle_message(self, command: int, decoded_data: bytes) -> None:
        """Handle incoming messages."""
        try:
            if command == SerialCommand.STATISTICS_STATUS_COMMAND.value:
                status_index = decoded_data[3]
                status_value_bytes = [
                    decoded_data[4],
                    decoded_data[5],
                    decoded_data[6],
                    decoded_data[7],
                ]
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

    def _update_statistics_status(self) -> None:
        """Send update status request for statistics items."""
        self.logger.info("Requesting for status ...")
        for index in self.error_items:
            self._status_update(STATISTICS_HEADER_BYTES, index)
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

    def _display_statistics_status(self) -> None:
        """Display statistics status."""
        print("Statistics Status:")
        statistics_data = []
        for index in self.error_items:
            item = self.error_items[index]
            last_updated = "N/A"
            if item.last_updated != 0:
                last_updated = datetime.datetime.fromtimestamp(
                    item.last_updated,
                    tz=datetime.UTC,
                ).strftime("%Y-%m-%d %H:%M:%S")
            statistics_data.append([item.message, f"{item.value:,}", last_updated])

        print("Statistics Counters:")
        print(
            tabulate(
                statistics_data,
                headers=["Counter", "Value", "Last Updated"],
                tablefmt="simple_grid",
            )
        )

        print("\nCommands Sent Stastitics:")
        print(
            tabulate(
                [
                    [SerialCommand(k).name, f"{v:,}"]
                    for k, v in self.ser.statistics.commands_sent.items()
                ],
                headers=["Command", "Count"],
                tablefmt="simple_grid",
            )
        )
        print(f"Total bytes sent: {self.ser.statistics.bytes_sent:,.0f}")

        print("\nCommands Received Stastitics:")
        print(
            tabulate(
                [
                    [SerialCommand(k).name, f"{v:,}"]
                    for k, v in self.ser.statistics.commands_received.items()
                ],
                headers=["Command", "Count"],
                tablefmt="simple_grid",
            )
        )
        print(f"Total bytes received: {self.ser.statistics.bytes_received:,.0f}")

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

        cdc_idx = _TASK_INDEX_BY_NAME["cdc_task"]
        uart_idx = _TASK_INDEX_BY_NAME["uart_event_task"]
        core0_total_time = (
            self.task_items[cdc_idx].absoulute_time
            + self.task_items[uart_idx].absoulute_time
        )
        print(f"\nCore 0 total time: {core0_total_time:,.3f}")

        idle_idx = _TASK_INDEX_BY_NAME["idle_task"]
        encoder_idx = _TASK_INDEX_BY_NAME["encoder_read_task"]
        adc_idx = _TASK_INDEX_BY_NAME["adc_read_task"]
        keypad_idx = _TASK_INDEX_BY_NAME["keypad_task"]
        process_idx = _TASK_INDEX_BY_NAME["process_outbound_task"]
        decode_idx = _TASK_INDEX_BY_NAME["decode_reception_task"]
        core1_total_time = (
            self.task_items[idle_idx].absoulute_time
            + self.task_items[encoder_idx].absoulute_time
            + self.task_items[adc_idx].absoulute_time
            + self.task_items[keypad_idx].absoulute_time
            + self.task_items[process_idx].absoulute_time
            + self.task_items[decode_idx].absoulute_time
        )
        print(f"Core 1 total time: {core1_total_time:,.3f}")

    def _handle_user_choice(self, choice: str) -> bool:
        """Handle user choice and return whether to continue."""
        if choice == "1":
            self._update_statistics_status()
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
            self._display_statistics_status()
            self._display_task_status()

            print("\nSelect an option:")
            print("1. Request statistics status")
            print("2. Request task status")
            print("3. Show status")
            print("4. Exit")

            choice = input("Enter choice (1, 2, 3 or 4): ")

            if not self._handle_user_choice(choice):
                return
