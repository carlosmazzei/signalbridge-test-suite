"""Status mode module."""

import datetime
import logging
import time
from dataclasses import dataclass

from rich import box
from rich.panel import Panel
from rich.table import Table

from base_test import (
    IDLE_TASK_INDEX,
    STATISTICS_DISPLAY_NAMES,
    STATISTICS_HEADER_BYTES,
    STATISTICS_ITEMS,
    TASK_CORE_AFFINITY,
    TASK_DISPLAY_NAMES,
    TASK_HEADER_BYTES,
    TASK_ITEMS,
    TASK_STACK_BYTES,
)
from serial_interface import SerialCommand, SerialInterface
from ui_console import console

logger = logging.getLogger(__name__)

# Reverse lookup: name -> index for TASK_ITEMS
_TASK_INDEX_BY_NAME = {name: idx for idx, name in TASK_ITEMS.items()}

_STACK_PCT_HIGH_THRESHOLD = 75  # % used → red
_STACK_PCT_MED_THRESHOLD = 50  # % used → yellow

# Statistics keys that represent error counters (value > 0 is bad)
_ERROR_STAT_NAMES = frozenset(STATISTICS_DISPLAY_NAMES) - {
    "bytes_sent",
    "bytes_received",
}


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
    absolute_time: int = 0
    percent_time: int = 0
    high_watermark: int = 0
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
                    task_item.absolute_time = abs_time
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

    @staticmethod
    def _fmt_timestamp(ts: float) -> str:
        """Format a Unix timestamp as a UTC datetime string, or 'N/A' if zero."""
        if ts == 0:
            return "N/A"
        return datetime.datetime.fromtimestamp(ts, tz=datetime.UTC).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def _display_statistics_status(self) -> None:
        """Display statistics status with Rich tables."""
        # --- Error / counter table ---
        stats_table = Table(
            title="Statistics Counters",
            box=box.SIMPLE_HEAD,
            show_lines=False,
        )
        stats_table.add_column("Counter", style="bold")
        stats_table.add_column("Value", justify="right")
        stats_table.add_column("Last Updated", style="dim")

        for idx, item in self.error_items.items():
            stat_name = STATISTICS_ITEMS[idx]
            is_error_counter = stat_name in _ERROR_STAT_NAMES
            value_str = f"{item.value:,}"
            if is_error_counter and item.value > 0:
                value_str = f"[red]{value_str}[/red]"
            elif is_error_counter:
                value_str = f"[green]{value_str}[/green]"
            stats_table.add_row(
                item.message, value_str, self._fmt_timestamp(item.last_updated)
            )

        console.print(stats_table)

        # --- Commands sent table ---
        sent_table = Table(
            title="Commands Sent",
            box=box.SIMPLE_HEAD,
            show_lines=False,
        )
        sent_table.add_column("Command", style="bold")
        sent_table.add_column("Count", justify="right")
        for k, v in self.ser.statistics.commands_sent.items():
            sent_table.add_row(SerialCommand(k).name, f"{v:,}")
        console.print(sent_table)
        console.print(
            f"  Total bytes sent: [cyan]{self.ser.statistics.bytes_sent:,}[/cyan]"
        )

        # --- Commands received table ---
        recv_table = Table(
            title="Commands Received",
            box=box.SIMPLE_HEAD,
            show_lines=False,
        )
        recv_table.add_column("Command", style="bold")
        recv_table.add_column("Count", justify="right")
        for k, v in self.ser.statistics.commands_received.items():
            recv_table.add_row(SerialCommand(k).name, f"{v:,}")
        console.print(recv_table)
        received = self.ser.statistics.bytes_received
        console.print(f"  Total bytes received: [cyan]{received:,}[/cyan]")

    def format_time_from_microseconds(self, microseconds: int) -> str:
        """Format time from microseconds."""
        milliseconds = microseconds / 1000
        seconds, ms = divmod(milliseconds, 1000)
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes):02}:{int(seconds):02}:{int(ms):03}"

    @staticmethod
    def _core_label(core: int) -> str:
        """Return a coloured core label, or 'N/A' for unpinned tasks."""
        if core == 0:
            return "[bright_blue]Core 0[/bright_blue]"
        if core == 1:
            return "[bright_magenta]Core 1[/bright_magenta]"
        return "[dim]N/A[/dim]"

    def _display_task_status(self) -> None:
        """Display task status with a Rich table."""
        task_table = Table(
            title="Task Status",
            box=box.SIMPLE_HEAD,
            show_lines=False,
        )
        task_table.add_column("Task", style="bold")
        task_table.add_column("Core", justify="center")
        task_table.add_column("Stack (B)", justify="right")
        task_table.add_column("Abs Time (mm:ss:ms)", justify="right")
        task_table.add_column("% Time", justify="right")
        task_table.add_column("High Watermark", justify="right")
        task_table.add_column("Stack %", justify="right")
        task_table.add_column("Last Updated", style="dim")

        for idx, item in self.task_items.items():
            task_name = TASK_ITEMS[idx]
            core = TASK_CORE_AFFINITY.get(task_name, -1)
            stack = TASK_STACK_BYTES.get(task_name, 0)
            formatted_time = self.format_time_from_microseconds(item.absolute_time)

            # For the idle/system slot the third field is min-free-heap (bytes)
            if idx == IDLE_TASK_INDEX:
                wm_label = f"[cyan]{item.high_watermark:,} B (heap)[/cyan]"
            else:
                wm_label = str(item.high_watermark)

            if idx == IDLE_TASK_INDEX or stack == 0 or item.high_watermark == 0:
                stack_pct_str = "[dim]N/A[/dim]"
            else:
                # Watermark is in words (FreeRTOS ARM Cortex-M0+, 4 bytes/word)
                pct = (stack - item.high_watermark * 4) / stack * 100
                if pct >= _STACK_PCT_HIGH_THRESHOLD:
                    color = "red"
                elif pct >= _STACK_PCT_MED_THRESHOLD:
                    color = "yellow"
                else:
                    color = "green"
                stack_pct_str = f"[{color}]{pct:.1f}%[/{color}]"

            stack_str = f"{stack:,}" if stack > 0 else "[dim]N/A[/dim]"
            task_table.add_row(
                item.name,
                self._core_label(core),
                stack_str,
                formatted_time,
                f"{item.percent_time}%",
                wm_label,
                stack_pct_str,
                self._fmt_timestamp(item.last_updated),
            )

        console.print(task_table)

        # --- Core totals (all tasks pinned to each core) ---
        core0_total_time = sum(
            self.task_items[_TASK_INDEX_BY_NAME[name]].absolute_time
            for name, core in TASK_CORE_AFFINITY.items()
            if core == 0
        )
        core1_total_time = sum(
            self.task_items[_TASK_INDEX_BY_NAME[name]].absolute_time
            for name, core in TASK_CORE_AFFINITY.items()
            if core == 1
        )

        summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        summary.add_column("label", style="dim")
        summary.add_column("value", justify="right", style="cyan")
        summary.add_row("Core 0 total time", f"{core0_total_time:,.3f}")
        summary.add_row("Core 1 total time", f"{core1_total_time:,.3f}")

        # Heap info from the idle/system slot
        idle_item = self.task_items.get(IDLE_TASK_INDEX)
        if idle_item is not None:
            heap_val = idle_item.high_watermark
            summary.add_row("Min free heap", f"{heap_val:,} bytes")

        console.print(summary)

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
            console.print("[yellow]Invalid choice, please try again.[/yellow]")
        return True

    def execute_test(self) -> None:
        """Execute status mode test."""
        while True:
            self._display_statistics_status()
            self._display_task_status()

            options = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
            options.add_column("key", style="bold cyan", width=4)
            options.add_column("action")
            options.add_row("[1]", "Request statistics status")
            options.add_row("[2]", "Request task status")
            options.add_row("[3]", "Refresh display")
            options.add_row("[4]", "Exit")
            console.print(Panel(options, title="Status Options", title_align="left"))

            choice = console.input("[bold]Enter choice:[/bold] ")

            if not self._handle_user_choice(choice):
                return
