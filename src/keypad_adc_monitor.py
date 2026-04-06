"""Keypad and ADC monitor module."""

from __future__ import annotations

import datetime
import logging
import threading
import time
from collections import deque

from rich import box
from rich.columns import Columns
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from serial_interface import SerialCommand, SerialInterface
from ui_console import console

logger = logging.getLogger(__name__)

ADC_HISTORY_SIZE: int = 10
KEYPAD_EVENT_HISTORY: int = 20
LIVE_REFRESH_PER_SEC: float = 2.0

_ADC_COLOUR_LOW_THRESHOLD: float = 0.25
_ADC_COLOUR_HIGH_THRESHOLD: float = 0.75

_SPARK_CHARS = "▁▂▃▄▅▆▇█"
_ADC_MAX: int = 4095


class KeypadAdcMonitor:
    """Monitor for keypad press/release events and ADC channel readings."""

    def __init__(self, ser: SerialInterface) -> None:
        """Initialise the monitor with a serial interface."""
        self._ser = ser
        self._lock = threading.Lock()
        # channel -> deque of (value, timestamp)
        self._adc_history: dict[int, deque[tuple[int, float]]] = {}
        # deque of (col, row, state, timestamp)
        self._keypad_events: deque[tuple[int, int, int, float]] = deque(
            maxlen=KEYPAD_EVENT_HISTORY
        )
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Message handler (called from the serial processing thread)
    # ------------------------------------------------------------------

    def handle_message(self, command: int, decoded_data: bytes) -> None:
        """Dispatch incoming frames to the appropriate handler."""
        try:
            if command == SerialCommand.KEY_COMMAND.value:
                col = (decoded_data[3] >> 4) & 0x0F
                row = (decoded_data[3] >> 1) & 0x07
                state = decoded_data[3] & 0x01
                ts = time.time()
                with self._lock:
                    self._keypad_events.append((col, row, state, ts))
                logger.debug("Keypad: col=%d row=%d state=%d", col, row, state)

            elif command == SerialCommand.ANALOG_COMMAND.value:
                channel = decoded_data[3]
                value = (decoded_data[4] << 8) | decoded_data[5]
                ts = time.time()
                with self._lock:
                    if channel not in self._adc_history:
                        self._adc_history[channel] = deque(maxlen=ADC_HISTORY_SIZE)
                    self._adc_history[channel].append((value, ts))
                logger.debug("ADC ch=%d value=%d", channel, value)

        except IndexError:
            logger.exception("Malformed message (command=%d)", command)

    # ------------------------------------------------------------------
    # Display builders
    # ------------------------------------------------------------------

    @staticmethod
    def _sparkline(values: list[int]) -> str:
        """Convert a list of 0-4095 ADC values into a sparkline string."""
        if not values:
            return ""
        lo, hi = min(values), max(values)
        span = hi - lo or 1
        chars = len(_SPARK_CHARS)
        return "".join(
            _SPARK_CHARS[min(int((v - lo) / span * chars), chars - 1)] for v in values
        )

    @staticmethod
    def _fmt_ts(ts: float) -> str:
        """Format a Unix timestamp as HH:MM:SS.mmm (UTC)."""
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.UTC)
        return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"

    def _build_adc_table(self) -> Table:
        """Build a Rich table showing per-channel ADC history."""
        table = Table(
            title="ADC Monitor",
            box=box.SIMPLE_HEAD,
            show_lines=False,
            min_width=52,
        )
        table.add_column("Ch", justify="right", style="bold cyan", width=4)
        table.add_column("Last Value", justify="right", width=11)
        table.add_column(f"Trend (last {ADC_HISTORY_SIZE})", width=12)
        table.add_column("Last Updated", style="dim", width=14)

        with self._lock:
            snapshot = {
                ch: list(hist) for ch, hist in sorted(self._adc_history.items())
            }

        if not snapshot:
            table.add_row("[dim]—[/dim]", "[dim]waiting…[/dim]", "", "")
            return table

        for channel, entries in snapshot.items():
            values = [v for v, _ in entries]
            last_val, last_ts = entries[-1]
            bar_pct = last_val / _ADC_MAX
            if bar_pct < _ADC_COLOUR_LOW_THRESHOLD:
                colour = "green"
            elif bar_pct < _ADC_COLOUR_HIGH_THRESHOLD:
                colour = "yellow"
            else:
                colour = "red"
            table.add_row(
                str(channel),
                f"[{colour}]{last_val:>5}[/]",
                self._sparkline(values),
                self._fmt_ts(last_ts),
            )
        return table

    def _build_keypad_table(self) -> Table:
        """Build a Rich table showing the keypad event log."""
        table = Table(
            title="Keypad Events",
            box=box.SIMPLE_HEAD,
            show_lines=False,
            min_width=44,
        )
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("Time", width=13)
        table.add_column("Col", justify="right", width=4)
        table.add_column("Row", justify="right", width=4)
        table.add_column("State", width=10)

        with self._lock:
            events = list(self._keypad_events)

        if not events:
            table.add_row("[dim]—[/dim]", "[dim]waiting…[/dim]", "", "", "")
            return table

        for idx, (col, row, state, ts) in enumerate(reversed(events), start=1):
            state_str = (
                "[bold green]PRESSED[/bold green]" if state else "[dim]RELEASED[/dim]"
            )
            table.add_row(str(idx), self._fmt_ts(ts), str(col), str(row), state_str)

        return table

    def _build_display(self) -> Panel:
        """Combine ADC and keypad tables into a single renderable panel."""
        adc = self._build_adc_table()
        keypad = self._build_keypad_table()
        body = Columns([adc, keypad], padding=(0, 2), equal=False)
        return Panel(
            body,
            title="[bold cyan]Keypad & ADC Monitor[/bold cyan]",
            subtitle="[dim]Press ENTER to exit[/dim]",
            padding=(1, 1),
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def execute_monitor(self) -> None:
        """Start the live monitor display; blocks until the user presses ENTER."""
        self._stop_event.clear()

        def _wait_for_enter() -> None:
            try:
                input()
            except (EOFError, OSError):
                pass
            finally:
                self._stop_event.set()

        input_thread = threading.Thread(target=_wait_for_enter, daemon=True)
        input_thread.start()

        with Live(
            self._build_display(),
            console=console,
            refresh_per_second=LIVE_REFRESH_PER_SEC,
            transient=False,
        ) as live:
            while not self._stop_event.is_set():
                live.update(self._build_display())
                time.sleep(1.0 / LIVE_REFRESH_PER_SEC)

        input_thread.join(timeout=1.0)
        logger.info("Keypad & ADC monitor exited.")
