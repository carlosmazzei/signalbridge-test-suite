"""Tests for BaseTest module."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import numpy as np
import pytest

from base_test import (
    DEFAULT_MESSAGE_LENGTH,
    HEADER_BYTES,
    STATISTICS_HEADER_BYTES,
    STATISTICS_ITEMS,
    TASK_HEADER_BYTES,
    TASK_ITEMS,
    BaseTest,
)
from serial_interface import SerialCommand, SerialInterface


@pytest.fixture
def mock_serial() -> Mock:
    """Fixture for a mocked SerialInterface."""
    ser = Mock(spec=SerialInterface)
    ser.baudrate = 115200
    return ser


@pytest.fixture
def base_test(mock_serial: Mock) -> BaseTest:
    """Fixture for BaseTest with a mocked serial interface."""
    return BaseTest(mock_serial)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------
class TestBaseTestInit:
    """Tests for BaseTest.__init__."""

    def test_attributes_initialized(
        self, base_test: BaseTest, mock_serial: Mock
    ) -> None:
        """All attributes should be set to correct initial values."""
        assert base_test.ser is mock_serial
        assert base_test.latency_msg_sent == {}
        assert base_test.latency_msg_received == {}
        assert isinstance(base_test._status_lock, type(threading.Lock()))

    def test_statistics_values_initialized_to_zero(self, base_test: BaseTest) -> None:
        """All statistics values should start at 0."""
        assert set(base_test._statistics_values.keys()) == set(STATISTICS_ITEMS.keys())
        assert all(v == 0 for v in base_test._statistics_values.values())

    def test_statistics_updated_at_initialized_to_zero(
        self, base_test: BaseTest
    ) -> None:
        """All statistics timestamps should start at 0.0."""
        assert all(v == 0.0 for v in base_test._statistics_updated_at.values())

    def test_task_values_initialized(self, base_test: BaseTest) -> None:
        """All task values should be initialized with zeroed sub-dicts."""
        for idx in TASK_ITEMS:
            assert idx in base_test._task_values
            assert base_test._task_values[idx]["absolute_time_us"] == 0
            assert base_test._task_values[idx]["percent_time"] == 0
            assert base_test._task_values[idx]["high_watermark"] == 0

    def test_task_updated_at_initialized_to_zero(self, base_test: BaseTest) -> None:
        """All task timestamps should start at 0.0."""
        assert all(v == 0.0 for v in base_test._task_updated_at.values())


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------
class TestPublish:
    """Tests for BaseTest.publish."""

    def test_publish_calls_write_and_flush(
        self, base_test: BaseTest, mock_serial: Mock
    ) -> None:
        """publish() must call ser.write() then ser.flush()."""
        base_test.publish(0, DEFAULT_MESSAGE_LENGTH)
        mock_serial.write.assert_called_once()
        mock_serial.flush.assert_called_once()

    def test_publish_payload_starts_with_header(
        self, base_test: BaseTest, mock_serial: Mock
    ) -> None:
        """The payload written should start with HEADER_BYTES."""
        base_test.publish(0, DEFAULT_MESSAGE_LENGTH)
        written = mock_serial.write.call_args[0][0]
        assert written[:2] == HEADER_BYTES

    def test_publish_counter_encoded_big_endian(
        self, base_test: BaseTest, mock_serial: Mock
    ) -> None:
        """Counter bytes should be big-endian encoded at bytes [3:5]."""
        counter = 300
        base_test.publish(counter, DEFAULT_MESSAGE_LENGTH)
        written = mock_serial.write.call_args[0][0]
        assert written[3:5] == counter.to_bytes(2, byteorder="big")

    def test_publish_records_send_time(self, base_test: BaseTest) -> None:
        """publish() should record the send timestamp in latency_msg_sent."""
        before = time.perf_counter()
        base_test.publish(42, DEFAULT_MESSAGE_LENGTH)
        after = time.perf_counter()
        assert 42 in base_test.latency_msg_sent
        assert before <= base_test.latency_msg_sent[42] <= after

    def test_publish_different_counters_stored_independently(
        self, base_test: BaseTest
    ) -> None:
        """Each counter should have its own entry in latency_msg_sent."""
        base_test.publish(1, DEFAULT_MESSAGE_LENGTH)
        base_test.publish(2, DEFAULT_MESSAGE_LENGTH)
        assert 1 in base_test.latency_msg_sent
        assert 2 in base_test.latency_msg_sent
        assert len(base_test.latency_msg_sent) == 2

    def test_publish_payload_length_matches_message_length(
        self, base_test: BaseTest, mock_serial: Mock
    ) -> None:
        """Payload should be exactly `message_length` bytes long."""
        for length in [6, 7, 8, 9, 10]:
            mock_serial.reset_mock()
            base_test.publish(0, length)
            written = mock_serial.write.call_args[0][0]
            assert len(written) == length


# ---------------------------------------------------------------------------
# handle_message — ECHO_COMMAND
# ---------------------------------------------------------------------------
class TestHandleMessageEcho:
    """Tests for BaseTest.handle_message, ECHO_COMMAND branch."""

    def _make_echo_data(self, counter: int) -> bytes:
        """Build a fake decoded_data for an ECHO_COMMAND with the given counter."""
        # bytes[3,4] hold the big-endian counter
        prefix = bytes([0x00, 0x00, 0x00])
        return prefix + counter.to_bytes(2, byteorder="big")

    def test_echo_command_stores_latency(self, base_test: BaseTest) -> None:
        """ECHO_COMMAND stores received latency for the correct counter."""
        counter = 5
        base_test.latency_msg_sent[counter] = time.perf_counter() - 0.01
        data = self._make_echo_data(counter)
        base_test.handle_message(SerialCommand.ECHO_COMMAND.value, data)
        assert counter in base_test.latency_msg_received
        assert base_test.latency_msg_received[counter] > 0

    def test_echo_command_index_error_does_not_raise(self, base_test: BaseTest) -> None:
        """IndexError should be caught silently."""
        # Too-short data triggers IndexError
        base_test.handle_message(SerialCommand.ECHO_COMMAND.value, bytes([0x00]))

    def test_echo_command_key_error_does_not_raise(self, base_test: BaseTest) -> None:
        """KeyError (counter not in sent dict) should be caught silently."""
        data = self._make_echo_data(999)  # counter not in sent dict
        base_test.handle_message(SerialCommand.ECHO_COMMAND.value, data)
        # Should not raise; counter not stored
        assert 999 not in base_test.latency_msg_received


# ---------------------------------------------------------------------------
# handle_message — STATISTICS_STATUS_COMMAND
# ---------------------------------------------------------------------------
class TestHandleMessageStatistics:
    """Tests for BaseTest.handle_message, STATISTICS_STATUS_COMMAND branch."""

    def _make_stats_data(self, index: int, value: int) -> bytes:
        """Build fake decoded_data for a statistics status message."""
        prefix = bytes([0x00, 0x00, 0x00, index])
        return prefix + value.to_bytes(4, byteorder="big")

    def test_statistics_stores_value(self, base_test: BaseTest) -> None:
        """Valid statistics status updates _statistics_values."""
        idx = 0
        expected_value = 42
        data = self._make_stats_data(idx, expected_value)
        base_test.handle_message(SerialCommand.STATISTICS_STATUS_COMMAND.value, data)
        assert base_test._statistics_values[idx] == expected_value

    def test_statistics_updates_timestamp(self, base_test: BaseTest) -> None:
        """Valid statistics status updates _statistics_updated_at."""
        idx = 2
        data = self._make_stats_data(idx, 7)
        before = time.perf_counter()
        base_test.handle_message(SerialCommand.STATISTICS_STATUS_COMMAND.value, data)
        assert base_test._statistics_updated_at[idx] >= before

    def test_statistics_unknown_index_not_stored(self, base_test: BaseTest) -> None:
        """Index not in STATISTICS_ITEMS should be ignored."""
        unknown_idx = 99
        data = self._make_stats_data(unknown_idx, 1)
        base_test.handle_message(SerialCommand.STATISTICS_STATUS_COMMAND.value, data)
        assert unknown_idx not in base_test._statistics_values

    def test_statistics_index_error_caught(self, base_test: BaseTest) -> None:
        """Short message should not raise."""
        base_test.handle_message(
            SerialCommand.STATISTICS_STATUS_COMMAND.value, bytes([0x00])
        )


# ---------------------------------------------------------------------------
# handle_message — TASK_STATUS_COMMAND
# ---------------------------------------------------------------------------
class TestHandleMessageTask:
    """Tests for BaseTest.handle_message, TASK_STATUS_COMMAND branch."""

    def _make_task_data(
        self, index: int, abs_time: int, perc_time: int, h_watermark: int
    ) -> bytes:
        prefix = bytes([0x00, 0x00, 0x00, index])
        return (
            prefix
            + abs_time.to_bytes(4, byteorder="big")
            + perc_time.to_bytes(4, byteorder="big")
            + h_watermark.to_bytes(4, byteorder="big")
        )

    def test_task_stores_values(self, base_test: BaseTest) -> None:
        """Task status message stores abs_time, perc_time, h_watermark."""
        idx = 0
        data = self._make_task_data(idx, 1000, 50, 512)
        base_test.handle_message(SerialCommand.TASK_STATUS_COMMAND.value, data)
        entry = base_test._task_values[idx]
        assert entry["absolute_time_us"] == 1000
        assert entry["percent_time"] == 50
        assert entry["high_watermark"] == 512

    def test_task_status_updates_timestamp(self, base_test: BaseTest) -> None:
        """Task status message updates _task_updated_at."""
        idx = 1
        data = self._make_task_data(idx, 0, 0, 0)
        before = time.perf_counter()
        base_test.handle_message(SerialCommand.TASK_STATUS_COMMAND.value, data)
        assert base_test._task_updated_at[idx] >= before

    def test_task_unknown_index_not_stored(self, base_test: BaseTest) -> None:
        """Unknown task index should be ignored."""
        data = self._make_task_data(99, 1000, 50, 512)
        base_test.handle_message(SerialCommand.TASK_STATUS_COMMAND.value, data)
        assert 99 not in base_test._task_values

    def test_task_index_error_caught(self, base_test: BaseTest) -> None:
        """Short message should not raise."""
        base_test.handle_message(SerialCommand.TASK_STATUS_COMMAND.value, bytes([0x00]))


# ---------------------------------------------------------------------------
# _calculate_test_results
# ---------------------------------------------------------------------------
class TestCalculateTestResults:
    """Tests for BaseTest._calculate_test_results."""

    def test_returns_zeros_when_no_results(self, base_test: BaseTest) -> None:
        """Empty received dict returns a zeroed result."""
        result = base_test._calculate_test_results(
            test=0, samples=10, waiting_time=0.05, bitrate=1000.0
        )
        assert result["latency_avg"] == 0
        assert result["latency_min"] == 0
        assert result["latency_max"] == 0
        assert result["latency_p95"] == 0
        assert result["dropped_messages"] == 0

    def test_calculates_correct_averages(self, base_test: BaseTest) -> None:
        """avg/min/max should match expected values from known latencies."""
        latencies = {0: 0.01, 1: 0.02, 2: 0.03}
        base_test.latency_msg_sent = dict.fromkeys(latencies, 0.0)
        base_test.latency_msg_received = dict(latencies)
        result = base_test._calculate_test_results(
            test=1, samples=3, waiting_time=0.0, bitrate=100.0
        )
        assert result["latency_avg"] == pytest.approx(0.02)
        assert result["latency_min"] == pytest.approx(0.01)
        assert result["latency_max"] == pytest.approx(0.03)

    def test_p95_latency_calculated(self, base_test: BaseTest) -> None:
        """p95 should be correct percentile of known values."""
        latencies = {i: float(i + 1) for i in range(20)}
        base_test.latency_msg_sent = dict.fromkeys(latencies, 0.0)
        base_test.latency_msg_received = dict(latencies)
        result = base_test._calculate_test_results(
            test=0, samples=20, waiting_time=0.0, bitrate=500.0
        )
        expected_p95 = float(np.percentile(list(latencies.values()), 95))
        assert result["latency_p95"] == pytest.approx(expected_p95)

    def test_dropped_messages_count(self, base_test: BaseTest) -> None:
        """dropped_messages = len(sent) - len(received)."""
        base_test.latency_msg_sent = {0: 0.0, 1: 0.0, 2: 0.0}
        base_test.latency_msg_received = {0: 0.01}
        result = base_test._calculate_test_results(
            test=0, samples=3, waiting_time=0.0, bitrate=0.0
        )
        assert result["dropped_messages"] == 2

    def test_result_dict_contains_all_fields(self, base_test: BaseTest) -> None:
        """Result dict must include all expected keys."""
        base_test.latency_msg_received = {0: 0.01}
        base_test.latency_msg_sent = {0: 0.0}
        result = base_test._calculate_test_results(
            test=2, samples=1, waiting_time=0.1, bitrate=5000.0, jitter=True
        )
        assert result["test"] == 2
        assert result["waiting_time"] == pytest.approx(0.1)
        assert result["samples"] == 1
        assert result["jitter"] is True
        assert result["bitrate"] == pytest.approx(5000.0)

    def test_zero_result_dict_contains_all_fields(self, base_test: BaseTest) -> None:
        """Zero result dict must include all expected keys."""
        result = base_test._calculate_test_results(
            test=0, samples=5, waiting_time=0.05, bitrate=9600.0, jitter=False
        )
        assert "test" in result
        assert "waiting_time" in result
        assert "samples" in result
        assert "latency_avg" in result
        assert "latency_min" in result
        assert "latency_max" in result
        assert "latency_p95" in result
        assert "jitter" in result
        assert "bitrate" in result
        assert "dropped_messages" in result


# ---------------------------------------------------------------------------
# _write_output_to_file
# ---------------------------------------------------------------------------
class TestWriteOutputToFile:
    """Tests for BaseTest._write_output_to_file."""

    def test_writes_json_to_file(self, base_test: BaseTest) -> None:
        """Must call json.dump with the correct data."""
        data = [{"test": 0, "latency_avg": 0.01}]
        m = mock_open()
        with patch("pathlib.Path.open", m):
            base_test._write_output_to_file(Path("output.json"), data)
        handle = m()
        written = "".join(call.args[0] for call in handle.write.call_args_list)
        parsed = json.loads(written)
        assert parsed == data

    def test_oserror_is_caught(self, base_test: BaseTest) -> None:
        """OSError during file write should not propagate."""
        with patch("pathlib.Path.open", side_effect=OSError("disk full")):
            base_test._write_output_to_file(Path("output.json"), [])


# ---------------------------------------------------------------------------
# _status_update
# ---------------------------------------------------------------------------
class TestStatusUpdate:
    """Tests for BaseTest._status_update."""

    def test_writes_correct_payload(
        self, base_test: BaseTest, mock_serial: Mock
    ) -> None:
        """Payload = header + [0x01] + index_byte."""
        header = STATISTICS_HEADER_BYTES
        index = 5
        base_test._status_update(header, index)
        expected = header + bytes([0x01]) + index.to_bytes(1, byteorder="big")
        mock_serial.write.assert_called_once_with(expected)

    def test_task_header_used_correctly(
        self, base_test: BaseTest, mock_serial: Mock
    ) -> None:
        """TASK_HEADER_BYTES should appear at the start of task update payloads."""
        base_test._status_update(TASK_HEADER_BYTES, 3)
        written = mock_serial.write.call_args[0][0]
        assert written[: len(TASK_HEADER_BYTES)] == TASK_HEADER_BYTES

    def test_index_big_endian_single_byte(
        self, base_test: BaseTest, mock_serial: Mock
    ) -> None:
        """Index should be encoded as a single byte."""
        base_test._status_update(STATISTICS_HEADER_BYTES, 10)
        written = mock_serial.write.call_args[0][0]
        # Format: header(2) + 0x01(1) + index(1)
        assert written[-1] == 10
        assert len(written) == len(STATISTICS_HEADER_BYTES) + 2


# ---------------------------------------------------------------------------
# _calculate_status_delta
# ---------------------------------------------------------------------------
class TestCalculateStatusDelta:
    """Tests for BaseTest._calculate_status_delta."""

    def _make_snapshot(self, stat_val: int = 0, task_val: int = 0) -> dict:
        statistics = dict.fromkeys(STATISTICS_ITEMS.values(), stat_val)
        tasks = {
            name: {
                "absolute_time_us": task_val,
                "percent_time": task_val,
                "high_watermark": task_val,
            }
            for name in TASK_ITEMS.values()
        }
        return {"statistics": statistics, "tasks": tasks}

    def test_zero_delta_when_snapshots_equal(self, base_test: BaseTest) -> None:
        """Delta should be 0 for all keys when before == after."""
        snap = self._make_snapshot(10, 100)
        delta = base_test._calculate_status_delta(snap, snap)
        assert all(v == 0 for v in delta["statistics"].values())

    def test_positive_delta_computed_correctly(self, base_test: BaseTest) -> None:
        """Statistics delta should be after - before."""
        before = self._make_snapshot(5, 0)
        after = self._make_snapshot(12, 0)
        delta = base_test._calculate_status_delta(before, after)
        assert all(v == 7 for v in delta["statistics"].values())

    def test_task_delta_computed_correctly(self, base_test: BaseTest) -> None:
        """Task delta should compute differences for each sub-field."""
        before = self._make_snapshot(0, 100)
        after = self._make_snapshot(0, 250)
        delta = base_test._calculate_status_delta(before, after)
        for task_delta in delta["tasks"].values():
            assert task_delta["absolute_time_us"] == 150
            assert task_delta["percent_time"] == 150
            assert task_delta["high_watermark"] == 150

    def test_delta_keys_match_statistics_items(self, base_test: BaseTest) -> None:
        """Statistics delta dict keys should match STATISTICS_ITEMS names."""
        snap = self._make_snapshot()
        delta = base_test._calculate_status_delta(snap, snap)
        assert set(delta["statistics"].keys()) == set(STATISTICS_ITEMS.values())

    def test_delta_keys_match_task_items(self, base_test: BaseTest) -> None:
        """Task delta dict keys should match TASK_ITEMS names."""
        snap = self._make_snapshot()
        delta = base_test._calculate_status_delta(snap, snap)
        assert set(delta["tasks"].keys()) == set(TASK_ITEMS.values())


# ---------------------------------------------------------------------------
# _get_user_input
# ---------------------------------------------------------------------------
class TestGetUserInput:
    """Tests for BaseTest._get_user_input."""

    def test_returns_default_on_empty_input(self, base_test: BaseTest) -> None:
        """Empty input (just Enter) should return the default value."""
        with patch("builtins.input", return_value=""):
            result = base_test._get_user_input("prompt", 42)
        assert result == 42

    def test_returns_converted_value_on_non_empty_input(
        self, base_test: BaseTest
    ) -> None:
        """Non-empty input should be converted to the type of default."""
        with patch("builtins.input", return_value="99"):
            result = base_test._get_user_input("prompt", 10)
        assert result == 99
        assert isinstance(result, int)

    def test_returns_default_for_whitespace_only(self, base_test: BaseTest) -> None:
        """Whitespace-only input should be treated as empty."""
        with patch("builtins.input", return_value="   "):
            result = base_test._get_user_input("prompt", 5)
        assert result == 5

    def test_float_conversion(self, base_test: BaseTest) -> None:
        """Float default causes float conversion."""
        with patch("builtins.input", return_value="3.14"):
            result = base_test._get_user_input("prompt", 0.0)
        assert result == pytest.approx(3.14)

    def test_includes_default_in_prompt(self, base_test: BaseTest) -> None:
        """Prompt string should mention the default value."""
        with patch("builtins.input", return_value="") as mock_input:
            base_test._get_user_input("Enter value", 77)
        call_arg = mock_input.call_args[0][0]
        assert "77" in call_arg
