"""Baud rate sweep test module."""

from __future__ import annotations

import datetime
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from alive_progress import alive_bar

from base_test import (
    DEFAULT_MESSAGE_LENGTH,
    DEFAULT_SAMPLES,
    DEFAULT_WAIT_TIME,
    MAX_SAMPLE_SIZE,
    BaseTest,
)
from const import TEST_RESULTS_FOLDER
from logger_config import setup_logging

if TYPE_CHECKING:
    from serial_interface import SerialInterface

DEFAULT_BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

setup_logging()

logger = logging.getLogger(__name__)


class BaudRateTest(BaseTest):
    """Run latency sweeps across multiple baud rates."""

    def __init__(self, ser: SerialInterface) -> None:
        """Initialize BaudRateTest class."""
        super().__init__(ser)

    def baud_rate_test(
        self,
        baud_rates: list[int],
        samples: int = DEFAULT_SAMPLES,
        wait_time: float = DEFAULT_WAIT_TIME,
        length: int = DEFAULT_MESSAGE_LENGTH,
        *,
        restore_baudrate: bool = True,
    ) -> None:
        """Sweep baud rates and run a latency burst at each rate."""
        current_datetime = datetime.datetime.now(tz=datetime.UTC)
        formatted_datetime = current_datetime.strftime("%Y%m%d_%H%M%S")
        output_filename = f"{formatted_datetime}_baud_sweep.json"
        file_path = Path(__file__).parent.parent / TEST_RESULTS_FOLDER / output_filename

        output_data: list[dict[str, Any]] = []
        original_baudrate = self.ser.baudrate
        bar_title = "Baud Rate Sweep"

        with alive_bar(samples * len(baud_rates), title=bar_title) as pbar:
            for j, rate in enumerate(baud_rates):
                self.latency_msg_sent.clear()
                self.latency_msg_received.clear()
                outstanding_messages: list[int] = []
                status_before = self._request_status_snapshot()

                logger.info("Test %d: setting baud rate to %d", j, rate)
                if not self.ser.set_baudrate(rate):
                    logger.info("Failed to set baud rate %d, skipping", rate)
                    continue

                # Re-register message handler after port reopen
                self.ser.set_message_handler(
                    lambda cmd, data, _: self.handle_message(cmd, data),
                )

                # Allow port to stabilize
                time.sleep(0.5)

                wire_bytes = length + 4
                min_uart_delay = (wire_bytes * 10) / rate

                burst_init_time = time.perf_counter()
                for i in range(samples):
                    self.publish(i, length)
                    time.sleep(min_uart_delay)
                    pbar()
                    outstanding_messages.append(
                        len(self.latency_msg_sent) - len(self.latency_msg_received)
                    )

                burst_elapsed_time = time.perf_counter() - burst_init_time
                logger.info("Waiting for %d seconds to collect results...", wait_time)
                time.sleep(wait_time)
                status_after = self._request_status_snapshot()
                outstanding_final = len(self.latency_msg_sent) - len(
                    self.latency_msg_received
                )

                bitrate = (samples * 8 * length) / burst_elapsed_time

                test_results = self._calculate_test_results(
                    test=j,
                    samples=samples,
                    waiting_time=min_uart_delay,
                    bitrate=bitrate,
                )
                test_results["baudrate"] = rate
                latency_results = list(self.latency_msg_received.values())
                output_data.append(
                    {
                        **test_results,
                        "results": latency_results,
                        "outstanding_messages": outstanding_messages,
                        "outstanding_max": max(
                            [*outstanding_messages, outstanding_final], default=0
                        ),
                        "outstanding_final": outstanding_final,
                        "status_before": status_before,
                        "status_after": status_after,
                        "status_delta": self._calculate_status_delta(
                            status_before, status_after
                        ),
                    }
                )

        if restore_baudrate:
            logger.info("Restoring original baud rate: %d", original_baudrate)
            self.ser.set_baudrate(original_baudrate)
            self.ser.set_message_handler(
                lambda cmd, data, _: self.handle_message(cmd, data),
            )

        self._write_output_to_file(file_path, output_data)

    def _show_baud_options(self) -> tuple[list[int], int, int, int]:
        """Show baud sweep options and return selected values."""
        print(f"Default baud rates: {DEFAULT_BAUD_RATES}")
        use_default = self._get_user_input(
            "(1/4) Use default baud rates? (True/False)",
            True,  # noqa: FBT003
        )

        if use_default:
            baud_rates = DEFAULT_BAUD_RATES
        else:
            baud_input = input(
                "Enter baud rates separated by commas "
                f"(default: {DEFAULT_BAUD_RATES}): "
            )
            if baud_input.strip():
                baud_rates = [int(b.strip()) for b in baud_input.split(",")]
            else:
                baud_rates = DEFAULT_BAUD_RATES

        num_samples = self._get_user_input(
            "(2/4) Enter number of samples per baud rate", DEFAULT_SAMPLES
        )
        if num_samples <= 0 or num_samples >= MAX_SAMPLE_SIZE:
            num_samples = DEFAULT_SAMPLES
            logger.info("Invalid number of samples. Using default value.")

        wait_time = self._get_user_input(
            "(3/4) Enter wait time after each burst (s)", DEFAULT_WAIT_TIME
        )
        if wait_time < 0:
            wait_time = DEFAULT_WAIT_TIME
            logger.info("Invalid wait time. Using default value.")

        message_length = self._get_user_input(
            "(4/4) Enter message length (min 6 to max 10)", DEFAULT_MESSAGE_LENGTH
        )
        if message_length < 6 or message_length > 10:  # noqa: PLR2004
            message_length = DEFAULT_MESSAGE_LENGTH
            logger.info("Invalid message length. Using default value.")

        return baud_rates, num_samples, wait_time, message_length

    def execute_baud_test(self) -> None:
        """Execute baud rate sweep test."""
        if self.ser is None:
            logger.info("No serial port found. Quitting test.")
            return

        try:
            baud_rates, samples, wait_time, length = self._show_baud_options()
            logger.info("Starting baud rate sweep: %s", baud_rates)
            time.sleep(wait_time)

            self.baud_rate_test(
                baud_rates=baud_rates,
                samples=samples,
                wait_time=wait_time,
                length=length,
            )

            logger.info("Baud rate sweep test ended")
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
