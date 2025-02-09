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

MAX_SAMPLE_SIZE = 65536  # 2 bytes counter
HEADER_BYTES = bytes([0x00, 0x34])
DEFAULT_WAIT_TIME = 3
DEFAULT_NUM_TIMES = 5
DEFAULT_MAX_WAIT = 0.1
DEFAULT_MIN_WAIT = 0
DEFAULT_MESSAGE_LENGTH = 10  # from 6 to 10
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

    def publish(self, iteration_counter: int, message_length: int) -> None:
        """
        Send messages.

        Args:
        ----
            iteration_counter (int): The current iteration count.
            message_length (int): The total length of the message to send

        """
        counter = iteration_counter.to_bytes(2, byteorder="big")
        # Build a byte stream for trailer with a specified length
        trailer = bytes([0x02] * (message_length - len(HEADER_BYTES) - 3))
        m_length = (len(trailer) + 2).to_bytes(1, byteorder="big")
        payload = HEADER_BYTES + m_length + counter + trailer

        self.latency_message[iteration_counter] = time.perf_counter()
        self.ser.write(payload)
        logger.info("Published (encoded) `%s`, counter %s", payload, iteration_counter)

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
        """
        Execute the main test given the desired parameters.

        Args:
        ----
            num_times (int): Number of test iterations.
            max_wait (float): Maximum wait time between messages.
            min_wait (float): Minimum wait time between messages.
            wait_time (float): Wait time after tests.
            samples (int): Number of samples per test.
            length (int): Length of the message to send.
            jitter (bool): Whether to add jitter to wait times.

        Raises:
        ------
            ValueError: If samples exceed MAX_SAMPLE_SIZE.

        """
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

                burst_elapsed_time = time.perf_counter() - burst_init_time
                # Calculated bitrate considering the total payload (HEADER_BYTES + 1)
                bitrate = (samples * 8 * length) / burst_elapsed_time

                test_results = self._calculate_test_results(
                    test=j,
                    samples=samples,
                    waiting_time=waiting_time,
                    bitrate=bitrate,
                    jitter=jitter,
                )
                latency_results_copy[j] = self.latency_results.copy()
                output_data.append({**test_results, "results": latency_results_copy[j]})

                logger.info("Waiting for %d seconds to collect results...", wait_time)
                time.sleep(wait_time)

        self._write_output_to_file(file_path, output_data)

    def _calculate_test_results(
        self,
        test: int,
        samples: int,
        waiting_time: float,
        bitrate: float,
        *,
        jitter: bool = False,
    ) -> dict[str, Any]:
        """
        Calculate test results including latency statistics and dropped messages.

        Args:
        ----
            test (int): Number of the test
            samples (int): Number of samples in the test.
            waiting_time (float): Waiting time between messages.
            bitrate (float): Average bitrate of each burst of samples.
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
                "bitrate": bitrate,
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
        print(f"Average bitrate: {bitrate}")

        return {
            "test": test,
            "waiting_time": waiting_time,
            "samples": samples,
            "latency_avg": latency_avg,
            "latency_min": latency_min,
            "latency_max": latency_max,
            "latency_p95": latency_p95,
            "jitter": jitter,
            "bitrate": bitrate,
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
                counter_bytes = [decoded_data[3], decoded_data[4]]
                counter = int.from_bytes(counter_bytes, byteorder="big")
                latency = time.perf_counter() - self.latency_message[counter]
                self.latency_results.append(latency)
                logger.info("Message %.5f latency: %.5f ms", counter, latency * 1e3)
            except IndexError:
                logger.info("Invalid message (Index Error)")

    def _get_user_input(self, prompt: str, default_value: Any) -> Any:
        """
        Get user input with default value.

        Args:
        ----
            prompt (str): The prompt to display.
            default_value (Any): The default value to use.

        """
        user_input = input(f"{prompt} (Press Enter to use default: {default_value}): ")
        return (
            default_value
            if user_input.strip() == ""
            else type(default_value)(user_input)
        )

    def _show_options(self) -> tuple[int, float, float, int, int, bool, int]:
        """
        Show options to user and get input.

        Returns
        -------
            tuple[int, float, float, int, int, bool]: The user input values.

        """
        num_times = self._get_user_input(
            "(1/6) Enter number of times", DEFAULT_NUM_TIMES
        )
        if num_times <= 0:
            num_times = DEFAULT_NUM_TIMES
            logger.info("Invalid number of times. Using default value.")

        min_wait = self._get_user_input(
            "(2/6) Enter min time to wait (ms)", DEFAULT_MIN_WAIT * 1000
        )
        if min_wait < 0:
            min_wait = DEFAULT_MIN_WAIT
            logger.info("Invalid min wait time. Using default value.")
        else:
            min_wait /= 1000

        max_wait = self._get_user_input(
            "(3/6) Enter max time to wait (ms)", DEFAULT_MAX_WAIT * 1000
        )
        if max_wait < 0:
            max_wait = DEFAULT_MAX_WAIT
            logger.info("Invalid max wait time. Using default value.")
        else:
            max_wait /= 1000

        num_samples = self._get_user_input(
            "(4/6) Enter number of samples", DEFAULT_SAMPLES
        )
        if num_samples <= 0 and num_samples < MAX_SAMPLE_SIZE:
            num_samples = DEFAULT_SAMPLES
            logger.info("Invalid number of samples. Using default value.")

        wait_time = self._get_user_input("Enter wait time (s)", DEFAULT_WAIT_TIME)
        if wait_time < 0:
            wait_time = DEFAULT_WAIT_TIME
            logger.info("Invalid wait time. Using default value.")

        jitter = self._get_user_input(
            "(5/6) Run test with jitter? (True/False)",
            False,  # noqa: FBT003
        )
        if not isinstance(jitter, bool):
            jitter = False
            logger.info("Invalid jitter value. Using default value.")

        message_length = self._get_user_input(
            "(6/6) Enter message length (min 6 to max 10)", DEFAULT_MESSAGE_LENGTH
        )
        if message_length < 6 or message_length > 10:  # noqa: PLR2004
            message_length = DEFAULT_MESSAGE_LENGTH
            logger.info("Invalid message length. Using default value.")

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

            print(f"Wait for {wait_time}s and start test ...")
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
