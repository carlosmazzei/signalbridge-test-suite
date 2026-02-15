"""Baud rate sweep test module."""

import datetime
import json
import logging
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
DEFAULT_MESSAGE_LENGTH = 10  # from 6 to 10
DEFAULT_SAMPLES = 255
DEFAULT_BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

setup_logging()

logger = logging.getLogger(__name__)


class BaudRateTest:
    """Run latency sweeps across multiple baud rates."""

    def __init__(self, ser: SerialInterface) -> None:
        """Initialize BaudRateTest class."""
        self.logger = logger
        self.ser = ser
        self.latency_msg_sent: dict[int, float] = {}
        self.latency_msg_received: dict[int, float] = {}

    def publish(self, iteration_counter: int, message_length: int) -> None:
        """Send one message with counter for roundtrip measurement."""
        counter = iteration_counter.to_bytes(2, byteorder="big")
        trailer = bytes([0x02] * (message_length - len(HEADER_BYTES) - 3))
        m_length = (len(trailer) + 2).to_bytes(1, byteorder="big")
        payload = HEADER_BYTES + m_length + counter + trailer

        self.latency_msg_sent[iteration_counter] = time.perf_counter()
        self.ser.write(payload)
        self.ser.flush()
        logger.info("Published (encoded) `%s`, counter %s", payload, iteration_counter)

    def _calculate_test_results(
        self,
        test: int,
        samples: int,
        waiting_time: float,
        bitrate: float,
        *,
        jitter: bool = False,
    ) -> dict[str, Any]:
        """Calculate latency statistics and dropped messages."""
        dropped_messages = len(self.latency_msg_sent) - len(self.latency_msg_received)
        logger.info("Dropped messages: %d ", dropped_messages)

        if not self.latency_msg_received:
            logger.info("No results collected for this test.")
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

        latencies = list(self.latency_msg_received.values())
        latency_avg = sum(latencies) / len(latencies)
        latency_min = min(latencies)
        latency_max = max(latencies)
        latency_p95 = np.percentile(latencies, 95)

        logger.info("Average latency: %f ms", latency_avg * 1e3)
        logger.info("Minimum latency: %f ms", latency_min * 1e3)
        logger.info("Maximum latency: %f ms", latency_max * 1e3)
        logger.info("P95 latency: %f ms", latency_p95 * 1e3)
        logger.info("Average bitrate: %s", bitrate)

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
        """Write test output data to JSON file."""
        try:
            with file_path.open("w", encoding="utf-8") as output_file:
                json.dump(output_data, output_file, indent=4)
                logger.info("Test results written to %s", file_path)
        except OSError:
            logger.exception("Error writing to file.")

    def handle_message(self, command: int, decoded_data: bytes) -> None:
        """Handle return message and store measured latency."""
        if command == SerialCommand.ECHO_COMMAND.value:
            try:
                counter_bytes = [decoded_data[3], decoded_data[4]]
                counter = int.from_bytes(counter_bytes, byteorder="big")
                latency = time.perf_counter() - self.latency_msg_sent[counter]
                self.latency_msg_received[counter] = latency
                logger.info("Message %d latency: %.5f ms", counter, latency * 1e3)
            except IndexError:
                logger.info("Invalid message (Index Error)")
            except KeyError:
                logger.debug(
                    "Ignoring stale echo response counter=%d (already cleared)",
                    counter,
                )

    def _get_user_input(self, prompt: str, default_value: Any) -> Any:
        """Get user input with default fallback."""
        user_input = input(f"{prompt} (Press Enter to use default: {default_value}): ")
        return (
            default_value
            if user_input.strip() == ""
            else type(default_value)(user_input)
        )

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

                burst_elapsed_time = time.perf_counter() - burst_init_time
                logger.info("Waiting for %d seconds to collect results...", wait_time)
                time.sleep(wait_time)

                bitrate = (samples * 8 * length) / burst_elapsed_time

                test_results = self._calculate_test_results(
                    test=j,
                    samples=samples,
                    waiting_time=min_uart_delay,
                    bitrate=bitrate,
                )
                test_results["baudrate"] = rate
                latency_results = list(self.latency_msg_received.values())
                output_data.append({**test_results, "results": latency_results})

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
