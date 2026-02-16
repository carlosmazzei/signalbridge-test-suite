"""Base test module with shared test infrastructure."""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from serial_interface import SerialCommand, SerialInterface

MAX_SAMPLE_SIZE = 65536  # 2 bytes counter
HEADER_BYTES = bytes([0x00, 0x34])
DEFAULT_WAIT_TIME = 3
DEFAULT_MESSAGE_LENGTH = 10  # from 6 to 10
DEFAULT_SAMPLES = 255
STATISTICS_HEADER_BYTES = bytes([0x00, 0x37])
TASK_HEADER_BYTES = bytes([0x00, 0x38])
STATUS_REQUEST_SPACING_S = 0.02
STATUS_REQUEST_TIMEOUT_S = 2.0

STATISTICS_ITEMS = {
    0: "queue_send_error",
    1: "queue_receive_error",
    2: "cdc_queue_send_error",
    3: "display_out_error",
    4: "led_out_error",
    5: "watchdog_error",
    6: "msg_malformed_error",
    7: "cobs_decode_error",
    8: "receive_buffer_overflow_error",
    9: "checksum_error",
    10: "buffer_overflow_error",
    11: "unknown_cmd_error",
    12: "bytes_sent",
    13: "bytes_received",
}

TASK_ITEMS = {
    0: "cdc_task",
    1: "cdc_write_task",
    2: "uart_event_task",
    3: "decode_reception_task",
    4: "process_outbound_task",
    5: "adc_read_task",
    6: "keypad_task",
    7: "encoder_read_task",
    8: "idle_task",
}

logger = logging.getLogger(__name__)


class BaseTest:
    """Base class with shared serial communication and status tracking."""

    def __init__(self, ser: SerialInterface) -> None:
        """Initialize base test infrastructure."""
        self.logger = logger
        self.ser = ser
        self.latency_msg_sent: dict[int, float] = {}
        self.latency_msg_received: dict[int, float] = {}
        self._status_lock = threading.Lock()
        self._statistics_values: dict[int, int] = dict.fromkeys(STATISTICS_ITEMS, 0)
        self._statistics_updated_at: dict[int, float] = dict.fromkeys(
            STATISTICS_ITEMS, 0.0
        )
        self._task_values = {
            idx: {"absolute_time_us": 0, "percent_time": 0, "high_watermark": 0}
            for idx in TASK_ITEMS
        }
        self._task_updated_at = dict.fromkeys(TASK_ITEMS, 0.0)

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
        elif command == SerialCommand.STATISTICS_STATUS_COMMAND.value:
            try:
                status_index = decoded_data[3]
                status_value = int.from_bytes(decoded_data[4:8], byteorder="big")
                if status_index in self._statistics_values:
                    now = time.perf_counter()
                    with self._status_lock:
                        self._statistics_values[status_index] = status_value
                        self._statistics_updated_at[status_index] = now
            except IndexError:
                logger.info("Invalid statistics status message")
        elif command == SerialCommand.TASK_STATUS_COMMAND.value:
            try:
                status_index = decoded_data[3]
                abs_time = int.from_bytes(decoded_data[4:8], byteorder="big")
                perc_time = int.from_bytes(decoded_data[8:12], byteorder="big")
                h_watermark = int.from_bytes(decoded_data[12:16], byteorder="big")
                if status_index in self._task_values:
                    now = time.perf_counter()
                    with self._status_lock:
                        self._task_values[status_index] = {
                            "absolute_time_us": abs_time,
                            "percent_time": perc_time,
                            "high_watermark": h_watermark,
                        }
                        self._task_updated_at[status_index] = now
            except IndexError:
                logger.info("Invalid task status message")

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

    def _status_update(self, header: bytes, index: int) -> None:
        """Send one status update command."""
        payload = header + bytes([0x01]) + index.to_bytes(1, byteorder="big")
        self.ser.write(payload)

    def _request_status_snapshot(
        self, timeout_s: float = STATUS_REQUEST_TIMEOUT_S
    ) -> dict[str, Any]:
        """Request device status snapshot and wait for responses."""
        if self.ser is None:
            return {
                "statistics": {},
                "tasks": {},
                "received": {"statistics": 0, "tasks": 0},
                "complete": False,
            }

        snapshot_marker = time.perf_counter()
        for index in STATISTICS_ITEMS:
            self._status_update(STATISTICS_HEADER_BYTES, index)
            time.sleep(STATUS_REQUEST_SPACING_S)
        for index in TASK_ITEMS:
            self._status_update(TASK_HEADER_BYTES, index)
            time.sleep(STATUS_REQUEST_SPACING_S)

        deadline = time.perf_counter() + timeout_s
        while time.perf_counter() < deadline:
            with self._status_lock:
                stats_received = sum(
                    1
                    for idx in STATISTICS_ITEMS
                    if self._statistics_updated_at[idx] >= snapshot_marker
                )
                tasks_received = sum(
                    1
                    for idx in TASK_ITEMS
                    if self._task_updated_at[idx] >= snapshot_marker
                )
            if stats_received == len(STATISTICS_ITEMS) and tasks_received == len(
                TASK_ITEMS
            ):
                break
            time.sleep(0.01)

        with self._status_lock:
            statistics = {
                name: self._statistics_values[idx]
                for idx, name in STATISTICS_ITEMS.items()
            }
            tasks = {name: self._task_values[idx] for idx, name in TASK_ITEMS.items()}
            stats_received = sum(
                1
                for idx in STATISTICS_ITEMS
                if self._statistics_updated_at[idx] >= snapshot_marker
            )
            tasks_received = sum(
                1 for idx in TASK_ITEMS if self._task_updated_at[idx] >= snapshot_marker
            )
        return {
            "statistics": statistics,
            "tasks": tasks,
            "received": {"statistics": stats_received, "tasks": tasks_received},
            "complete": (
                stats_received == len(STATISTICS_ITEMS)
                and tasks_received == len(TASK_ITEMS)
            ),
        }

    def _calculate_status_delta(
        self, before: dict[str, Any], after: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate delta between two status snapshots."""
        statistics_delta = {
            key: after["statistics"].get(key, 0) - before["statistics"].get(key, 0)
            for key in STATISTICS_ITEMS.values()
        }
        tasks_delta = {}
        for task in TASK_ITEMS.values():
            before_task = before["tasks"].get(task, {})
            after_task = after["tasks"].get(task, {})
            tasks_delta[task] = {
                "absolute_time_us": after_task.get("absolute_time_us", 0)
                - before_task.get("absolute_time_us", 0),
                "percent_time": after_task.get("percent_time", 0)
                - before_task.get("percent_time", 0),
                "high_watermark": after_task.get("high_watermark", 0)
                - before_task.get("high_watermark", 0),
            }
        return {"statistics": statistics_delta, "tasks": tasks_delta}

    def _get_user_input(self, prompt: str, default_value: Any) -> Any:
        """Get user input with default fallback."""
        user_input = input(f"{prompt} (Press Enter to use default: {default_value}): ")
        return (
            default_value
            if user_input.strip() == ""
            else type(default_value)(user_input)
        )
