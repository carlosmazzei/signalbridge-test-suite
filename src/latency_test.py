"""Latency Test Module."""

import datetime
import json
import logging
import random
import time
from pathlib import Path
from typing import Any

import numpy as np
from alive_progress import alive_bar

from const import TEST_RESULTS_FOLDER
from logger_config import setup_logging
from serial_interface import SerialCommand, SerialInterface

MAX_SAMPLE_SIZE = 255
HEADER_BYTES = bytes([0x00, 0x34, 0x03, 0x01, 0x02])
DEFAULT_WAIT_TIME = 3
DEFAULT_NUM_TIMES = 5
DEFAULT_MAX_WAIT = 0.1
DEFAULT_MIN_WAIT = 0
DEFAULT_SAMPLES = 255


setup_logging()

logger = logging.getLogger(__name__)


class LatencyTest:
    """Latency test class. Implement a roundtrip message to measure timing."""

    def __init__(self, ser: SerialInterface) -> None:
        """
        Initialize Latency Test Class.

        Args:
        ----
            ser (SerialInterface): The serial interface for communication.
            logger (Logger): The logger for recording events.

        """
        self.logger = logger
        self.ser = ser
        self.latency_message: list[float] = [0.0] * MAX_SAMPLE_SIZE
        self.latency_results: list[float] = []

    def publish(self, iteration_counter: int) -> None:
        """
        Send messages.

        Args:
        ----
            iteration_counter (int): The current iteration count.

        """
        counter = iteration_counter.to_bytes(1, byteorder="big")
        payload = HEADER_BYTES + counter

        start_time = time.time()
        self.latency_message[iteration_counter] = start_time
        self.ser.write(payload)
        logger.info("Published (encoded) `%s`, counter %s", payload, iteration_counter)

    def main_test(
        self,
        num_times: int = DEFAULT_NUM_TIMES,
        max_wait: float = DEFAULT_MAX_WAIT,
        min_wait: float = DEFAULT_MIN_WAIT,
        samples: int = DEFAULT_SAMPLES,
        *,
        jitter: bool = False,
    ) -> None:
        """
        Execute the main test given the desired parameters.

        Args:
        ----
            num_times (int): Number of test iterations.
            max_wait (float): Maximum wait time between messages.
            min_wait (float): Minimum wait time between messages.
            samples (int): Number of samples per test.
            jitter (bool): Whether to add jitter to wait times.

        Raises:
        ------
            ValueError: If samples exceed MAX_SAMPLE_SIZE.

        """
        if samples > MAX_SAMPLE_SIZE:
            msg = f"Samples must be less than or equal to {MAX_SAMPLE_SIZE}"
            raise ValueError(msg)

        current_datetime = datetime.datetime.now(tz=datetime.UTC)
        formatted_datetime = current_datetime.strftime("%Y%m%d_%H%M%S")
        output_filename = f"{formatted_datetime}_output.json"
        file_path = Path(__file__).parent.parent / TEST_RESULTS_FOLDER / output_filename

        output_data: list[dict[str, Any]] = []
        latency_results_copy: list[list[float]] = [[] for _ in range(num_times)]
        bar_title = f"Test / Jitter: {jitter}"

        with alive_bar(samples * num_times, title=bar_title) as pbar:
            for j in range(num_times):
                self.latency_results.clear()
                waiting_time = min_wait + (max_wait - min_wait) * (j / (num_times - 1))
                print(f"Test {j}, waiting time: {waiting_time} s")
                random_max = (max_wait - min_wait) * 0.2

                for i in range(samples):
                    self.publish(i)
                    if jitter:
                        time.sleep(
                            waiting_time + random.uniform(0, random_max),  # noqa: S311
                        )
                    else:
                        time.sleep(waiting_time)
                    pbar()

                test_results = self._calculate_test_results(
                    test=j,
                    samples=samples,
                    waiting_time=waiting_time,
                    jitter=jitter,
                )
                latency_results_copy[j] = self.latency_results.copy()
                output_data.append({**test_results, "results": latency_results_copy[j]})

                print(f"Waiting for {DEFAULT_WAIT_TIME} seconds to collect results...")
                time.sleep(DEFAULT_WAIT_TIME)

        self._write_output_to_file(file_path, output_data)

    def _calculate_test_results(
        self, test: int, samples: int, waiting_time: float, *, jitter: bool = False
    ) -> dict[str, Any]:
        """
        Calculate test results including latency statistics and dropped messages.

        Args:
        ----
            test (int): Number of the test
            samples (int): Number of samples in the test.
            waiting_time (float): Waiting time between messages.
            jitter (bool): Whether to add jitter to wait times.

        Returns:
        -------
            dict[str, Any]: A dictionary containing test results.

        """
        dropped_messages = samples - len(self.latency_results)
        print(f"Dropped messages: {dropped_messages}")

        if not self.latency_results:
            print("No results collected for this test.")
            return {
                "test": test,
                "waiting_time": waiting_time,
                "samples": samples,
                "latency_avg": 0,
                "latency_min": 0,
                "latency_max": 0,
                "latency_p95": 0,
                "jitter": jitter,
                "dropped_messages": dropped_messages,
            }

        latency_avg = sum(self.latency_results) / len(self.latency_results)
        latency_min = min(self.latency_results)
        latency_max = max(self.latency_results)
        latency_p95 = np.percentile(self.latency_results, 95)

        print(f"Average latency: {latency_avg * 1e3} ms")
        print(f"Minimum latency: {latency_min * 1e3} ms")
        print(f"Maximum latency: {latency_max * 1e3} ms")
        print(f"P95 latency: {latency_p95 * 1e3} ms")

        return {
            "test": test,
            "waiting_time": waiting_time,
            "samples": samples,
            "latency_avg": latency_avg,
            "latency_min": latency_min,
            "latency_max": latency_max,
            "latency_p95": latency_p95,
            "jitter": jitter,
            "dropped_messages": dropped_messages,
        }

    def _write_output_to_file(
        self,
        file_path: Path,
        output_data: list[dict[str, Any]],
    ) -> None:
        """
        Write test output data to a JSON file.

        Args:
        ----
            file_path (Path): The path to the output file.
            output_data (list[dict[str, Any]]): The data to write to the file.

        """
        try:
            with file_path.open("w", encoding="utf-8") as output_file:
                json.dump(output_data, output_file, indent=4)
                logger.info("Test results written to %s", file_path)
        except OSError:
            logger.exception("Error writing to file.")

    def handle_message(self, command: int, decoded_data: bytes) -> None:
        """
        Handle the return message. Calculate roundtrip time and store.

        Args:
        ----
            command (int): The command received.
            decoded_data (bytes): The decoded data received.

        """
        if command == SerialCommand.ECHO_COMMAND.value:
            try:
                counter = decoded_data[5]
                latency = time.time() - self.latency_message[counter]
                self.latency_results.append(latency)
                logger.info("Message %.5f latency: %.5f ms", counter, latency * 1e3)
            except IndexError:
                logger.info("Invalid message (Index Error)")

    def execute_test(self) -> None:
        """Execute main test function."""
        if self.ser is None:
            logger.info("No serial port found. Quitting test.")
            return

        try:
            logger.info(
                "Waiting to start test for %s \
                    seconds (press CTRL+C to interrupt test)...",
                DEFAULT_WAIT_TIME,
            )
            time.sleep(DEFAULT_WAIT_TIME)

            # Run the test without jitter
            self.main_test(jitter=False)

            # Run the test with jitter
            self.main_test(jitter=True)

            logger.info("Test ended")
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
