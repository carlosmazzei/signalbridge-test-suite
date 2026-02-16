"""Latency Test Module."""

import datetime
import logging
import random
import time
from pathlib import Path
from typing import Any

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
from serial_interface import SerialInterface

DEFAULT_NUM_TIMES = 5
DEFAULT_MAX_WAIT = 0.1
DEFAULT_MIN_WAIT = 0

setup_logging()

logger = logging.getLogger(__name__)


class LatencyTest(BaseTest):
    """Latency test class. Implement a roundtrip message to measure timing."""

    def __init__(self, ser: SerialInterface) -> None:
        """Initialize Latency Test Class."""
        super().__init__(ser)

    def main_test(  # noqa: PLR0913
        self,
        num_times: int = DEFAULT_NUM_TIMES,
        max_wait: float = DEFAULT_MAX_WAIT,
        min_wait: float = DEFAULT_MIN_WAIT,
        wait_time: float = DEFAULT_WAIT_TIME,
        samples: int = DEFAULT_SAMPLES,
        length: int = DEFAULT_MESSAGE_LENGTH,
        *,
        jitter: bool = False,
    ) -> None:
        """Execute the main test given the desired parameters."""
        current_datetime = datetime.datetime.now(tz=datetime.UTC)
        formatted_datetime = current_datetime.strftime("%Y%m%d_%H%M%S")
        output_filename = f"{formatted_datetime}_output.json"
        file_path = Path(__file__).parent.parent / TEST_RESULTS_FOLDER / output_filename

        output_data: list[dict[str, Any]] = []
        latency_results_copy: list[list[float]] = [[] for _ in range(num_times)]
        bar_title = f"Test / Jitter: {jitter}"

        # Minimum delay for UART TX buffer to drain: COBS adds ~2 bytes overhead,
        # and 8N1 encoding means 10 bits per byte on the wire.
        wire_bytes = length + 4  # payload + COBS overhead + delimiter
        min_uart_delay = (wire_bytes * 10) / self.ser.baudrate
        logger.info(
            "Minimum UART drain time: %.3f ms (baud=%d, wire_bytes=%d)",
            min_uart_delay * 1e3,
            self.ser.baudrate,
            wire_bytes,
        )

        with alive_bar(samples * num_times, title=bar_title) as pbar:
            for j in range(num_times):
                self.latency_msg_sent.clear()
                self.latency_msg_received.clear()
                outstanding_messages: list[int] = []
                status_before = self._request_status_snapshot()
                raw_wait = min_wait + (max_wait - min_wait) * (j / (num_times - 1))
                waiting_time = max(raw_wait, min_uart_delay)
                logger.info("Test %s, waiting time: %d s", j, waiting_time)
                random_max = (max_wait - min_wait) * 0.2

                burst_init_time = time.perf_counter()
                for i in range(samples):
                    self.publish(i, length)
                    if jitter:
                        time.sleep(
                            waiting_time + random.uniform(0, random_max),  # noqa: S311
                        )
                    else:
                        time.sleep(waiting_time)
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
                # Calculated bitrate considering the total payload (HEADER_BYTES + 1)
                bitrate = (samples * 8 * length) / burst_elapsed_time

                test_results = self._calculate_test_results(
                    test=j,
                    samples=samples,
                    waiting_time=waiting_time,
                    bitrate=bitrate,
                    jitter=jitter,
                )
                latency_results_copy[j] = list(self.latency_msg_received.values())
                output_data.append(
                    {
                        **test_results,
                        "results": latency_results_copy[j],
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

        self._write_output_to_file(file_path, output_data)

    def _default_min_wait_ms(
        self, message_length: int = DEFAULT_MESSAGE_LENGTH
    ) -> float:
        """Compute a baud-rate based default minimum wait in milliseconds."""
        if self.ser is None:
            return DEFAULT_MIN_WAIT * 1000

        baudrate = getattr(self.ser, "baudrate", 0)
        if not isinstance(baudrate, int | float) or baudrate <= 0:
            return DEFAULT_MIN_WAIT * 1000

        wire_bytes = message_length + 4  # payload + COBS overhead + delimiter
        return (wire_bytes * 10 / baudrate) * 1000

    def _show_options(self) -> tuple[int, float, float, int, int, bool, int]:
        """Show options to user and get input."""
        num_times = self._get_user_input(
            "(1/7) Enter number of times", DEFAULT_NUM_TIMES
        )
        if num_times <= 0:
            num_times = DEFAULT_NUM_TIMES
            logger.info("Invalid number of times. Using default value.")

        message_length = self._get_user_input(
            "(2/7) Enter message length (min 6 to max 10)", DEFAULT_MESSAGE_LENGTH
        )
        if message_length < 6 or message_length > 10:  # noqa: PLR2004
            message_length = DEFAULT_MESSAGE_LENGTH
            logger.info("Invalid message length. Using default value.")

        default_min_wait_ms = self._default_min_wait_ms(message_length)
        min_wait = self._get_user_input(
            "(3/7) Enter min time to wait (ms)", default_min_wait_ms
        )
        if min_wait < 0:
            min_wait = default_min_wait_ms / 1000
            logger.info("Invalid min wait time. Using default value.")
        else:
            min_wait /= 1000

        max_wait = self._get_user_input(
            "(4/7) Enter max time to wait (ms)", DEFAULT_MAX_WAIT * 1000
        )
        if max_wait < 0:
            max_wait = DEFAULT_MAX_WAIT
            logger.info("Invalid max wait time. Using default value.")
        else:
            max_wait /= 1000

        num_samples = self._get_user_input(
            "(5/7) Enter number of samples", DEFAULT_SAMPLES
        )
        if num_samples <= 0 and num_samples < MAX_SAMPLE_SIZE:
            num_samples = DEFAULT_SAMPLES
            logger.info("Invalid number of samples. Using default value.")

        wait_time = self._get_user_input("(6/7) Enter wait time (s)", DEFAULT_WAIT_TIME)
        if wait_time < 0:
            wait_time = DEFAULT_WAIT_TIME
            logger.info("Invalid wait time. Using default value.")

        jitter = self._get_user_input(
            "(7/7) Run test with jitter? (True/False)",
            False,  # noqa: FBT003
        )
        if not isinstance(jitter, bool):
            jitter = False
            logger.info("Invalid jitter value. Using default value.")

        return (
            num_times,
            min_wait,
            max_wait,
            num_samples,
            wait_time,
            jitter,
            message_length,
        )

    def execute_test(self) -> None:
        """Execute main test function."""
        if self.ser is None:
            logger.info("No serial port found. Quitting test.")
            return

        try:
            (
                num_times,
                min_wait,
                max_wait,
                num_samples,
                wait_time,
                jitter,
                message_length,
            ) = self._show_options()

            logger.info("Wait for %d s and start test ...", wait_time)
            time.sleep(wait_time)

            # Run the test with user-defined parameters
            self.main_test(
                num_times=num_times,
                max_wait=max_wait,
                min_wait=min_wait,
                samples=num_samples,
                wait_time=wait_time,
                jitter=jitter,
                length=message_length,
            )

            logger.info("Test ended")
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
