"""Unit tests for src/latency_test.py."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import numpy as np
import pytest

from base_test import (
    DEFAULT_MESSAGE_LENGTH,
    DEFAULT_SAMPLES,
    DEFAULT_WAIT_TIME,
    HEADER_BYTES,
)
from latency_test import (
    LatencyTest,
)
from serial_interface import SerialCommand, SerialInterface


@pytest.fixture
def latency_tester() -> LatencyTest:
    """LatencyTest with a mocked SerialInterface."""
    ser = Mock(spec=SerialInterface)
    return LatencyTest(ser)


def test_publish_builds_correct_payload_and_records_time(
    latency_tester: LatencyTest,
) -> None:
    """publish() should build a properly formatted payload and call write()."""
    ser_mock: Mock = latency_tester.ser  # type: ignore[assignment]

    counter = 5
    message_length = 8

    with patch("base_test.time.perf_counter", return_value=123.456):
        latency_tester.publish(counter, message_length)

    # Verify time recorded after write and flush
    assert pytest.approx(latency_tester.latency_msg_sent[counter]) == pytest.approx(
        123.456
    )

    # Verify payload structure sent to serial, followed by flush
    assert ser_mock.write.call_count == 1
    assert ser_mock.flush.call_count == 1
    (payload,), _ = ser_mock.write.call_args
    assert isinstance(payload, (bytes, bytearray))
    assert len(payload) == message_length
    # Header
    assert payload[:2] == HEADER_BYTES
    # Length byte equals trailer length + 2 (for 2-byte counter)
    expected_trailer_len = message_length - len(HEADER_BYTES) - 3
    assert payload[2] == expected_trailer_len + 2
    # Counter bytes (big-endian)
    assert payload[3:5] == counter.to_bytes(2, "big")
    # Trailer is 0x02 pattern
    assert payload[5:] == bytes([0x02] * expected_trailer_len)


def test_calculate_test_results_with_data(latency_tester: LatencyTest) -> None:
    """_calculate_test_results returns stats when results exist."""
    # Pre-populate received latencies
    latency_tester.latency_msg_sent = {0: 0.0, 1: 0.0, 2: 0.0}
    latency_tester.latency_msg_received = {0: 0.10, 1: 0.20, 2: 0.30}

    ptest = 1
    psamples = 3
    pwaiting_time = 0.05
    pbitrate = 100.0
    pjitter = True

    res = latency_tester._calculate_test_results(
        test=ptest,
        samples=psamples,
        waiting_time=pwaiting_time,
        bitrate=pbitrate,
        jitter=pjitter,
    )

    assert res["test"] == ptest
    assert res["samples"] == psamples
    assert res["waiting_time"] == pytest.approx(pwaiting_time)
    assert res["jitter"] is pjitter
    assert res["bitrate"] == pytest.approx(pbitrate)
    assert res["dropped_messages"] == 0
    assert pytest.approx(res["latency_avg"], rel=1e-6) == pytest.approx(
        np.mean([0.10, 0.20, 0.30])
    )
    assert res["latency_min"] == pytest.approx(0.10)
    assert res["latency_max"] == pytest.approx(0.30)
    assert pytest.approx(res["latency_p95"], rel=1e-6) == pytest.approx(
        float(np.percentile([0.10, 0.20, 0.30], 95))
    )


def test_calculate_test_results_no_data(latency_tester: LatencyTest) -> None:
    """_calculate_test_results handles empty results and reports drops."""
    # Simulate that 3 messages were sent but none received
    latency_tester.latency_msg_sent = {0: 0.0, 1: 0.0, 2: 0.0}
    latency_tester.latency_msg_received = {}

    res = latency_tester._calculate_test_results(
        test=0, samples=3, waiting_time=0.1, bitrate=50.0, jitter=False
    )

    assert res == {
        "test": 0,
        "waiting_time": 0.1,
        "samples": 3,
        "latency_avg": 0,
        "latency_min": 0,
        "latency_max": 0,
        "latency_p95": 0,
        "jitter": False,
        "bitrate": 50.0,
        "dropped_messages": 3,
    }


def test_write_output_to_file_success(tmp_path: Path) -> None:
    """_write_output_to_file writes JSON data to the given path."""
    tester = LatencyTest(Mock(spec=SerialInterface))
    output_file = tmp_path / "out.json"
    payload = [{"a": 1}, {"b": 2}]

    tester._write_output_to_file(output_file, payload)

    assert output_file.exists()
    data = json.loads(output_file.read_text())
    assert data == payload


def test_write_output_to_file_oserror_logs(caplog: pytest.LogCaptureFixture) -> None:
    """_write_output_to_file logs exceptions when file writing fails."""
    tester = LatencyTest(Mock(spec=SerialInterface))
    bad_path = Path("/cannot/open/this.json")

    with (
        patch.object(Path, "open", side_effect=OSError),
        caplog.at_level(logging.ERROR),
    ):
        logger = logging.getLogger("base_test")
        logger.addHandler(caplog.handler)
        tester._write_output_to_file(bad_path, [{"x": 1}])
        logger.removeHandler(caplog.handler)
    assert "Error writing to file." in caplog.text


def test_handle_message_valid_updates_latency(latency_tester: LatencyTest) -> None:
    """handle_message computes latency and stores it by counter."""
    counter = 7
    # Simulate that the message with this counter was sent at t=1.0
    latency_tester.latency_msg_sent[counter] = 1.0

    # perf_counter now returns 2.5, so latency should be 1.5
    with patch("base_test.time.perf_counter", return_value=2.5):
        latency_tester.handle_message(
            SerialCommand.ECHO_COMMAND.value, b"\x00\x00\x00\x00\x07"
        )

    assert pytest.approx(latency_tester.latency_msg_received[counter]) == pytest.approx(
        1.5
    )


def test_handle_message_index_error_logged(caplog: pytest.LogCaptureFixture) -> None:
    """handle_message logs on malformed data (IndexError)."""
    tester = LatencyTest(Mock(spec=SerialInterface))

    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("base_test")
        logger.addHandler(caplog.handler)
        tester.handle_message(SerialCommand.ECHO_COMMAND.value, b"\x01\x02")
        logger.removeHandler(caplog.handler)
    assert "Invalid message (Index Error)" in caplog.text


def test_get_user_input_default_and_casting() -> None:
    """_get_user_input returns default on blank and casts otherwise."""
    tester = LatencyTest(Mock(spec=SerialInterface))
    with patch("builtins.input", return_value=" "):
        pinput = 3
        assert tester._get_user_input("prompt", pinput) == pinput
    with patch("builtins.input", return_value="7"):
        preturn = 7
        assert tester._get_user_input("prompt", pinput) == preturn
    with patch("builtins.input", return_value="1.5"):
        assert pytest.approx(tester._get_user_input("prompt", 0.5)) == pytest.approx(
            1.5
        )


def test_show_options_happy_path() -> None:
    """_show_options converts ms inputs to seconds and validates ranges."""
    tester = LatencyTest(Mock(spec=SerialInterface))
    with patch.object(
        LatencyTest,
        "_get_user_input",
        side_effect=[2, 6, 100, 200, 10, 1, True],
    ):
        res = tester._show_options()
    # Param: num_times, min_wait(s), max_wait(s), samples, wait_time(s), jitter, msg_len
    assert res == (2, 0.1, 0.2, 10, 1, True, 6)


def test_show_options_invalid_values(caplog: pytest.LogCaptureFixture) -> None:
    """_show_options falls back to defaults on invalid values."""
    tester = LatencyTest(Mock(spec=SerialInterface))
    tester.ser.baudrate = 115200  # type: ignore[union-attr]
    expected_min_wait = ((DEFAULT_MESSAGE_LENGTH + 4) * 10) / 115200

    with (
        patch.object(
            LatencyTest,
            "_get_user_input",
            side_effect=[-1, 100, -10, -20, -1, -1, "nope"],
        ),
        caplog.at_level(logging.INFO),
    ):
        logger = logging.getLogger("latency_test")
        logger.addHandler(caplog.handler)
        res = tester._show_options()
        logger.removeHandler(caplog.handler)

    # num_times -> default 5; min_wait -> baud-derived default; max_wait -> default 0.1
    # samples -> default 255; wait_time -> default 3; jitter -> coerced False;
    # message_length -> default 10
    assert res == (
        5,
        pytest.approx(expected_min_wait),
        0.1,
        DEFAULT_SAMPLES,
        DEFAULT_WAIT_TIME,
        False,
        DEFAULT_MESSAGE_LENGTH,
    )
    assert "Invalid number of times" in caplog.text
    assert "Invalid min wait time" in caplog.text
    assert "Invalid max wait time" in caplog.text
    assert "Invalid number of samples" in caplog.text
    assert "Invalid wait time" in caplog.text
    assert "Invalid jitter value" in caplog.text
    assert "Invalid message length" in caplog.text


def test_execute_test_no_serial_logs_and_returns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """execute_test exits early when no serial interface is provided."""
    tester = LatencyTest(ser=None)  # type: ignore[arg-type]

    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("latency_test")
        logger.addHandler(caplog.handler)
        tester.execute_test()
        logger.removeHandler(caplog.handler)
    assert "No serial port found. Quitting test." in caplog.text


def test_main_test_collects_and_writes_output() -> None:
    """main_test runs loops, computes bitrate, and writes output via helper."""
    mock_ser = Mock(spec=SerialInterface)
    mock_ser.baudrate = 115200
    tester = LatencyTest(mock_ser)

    # Replace progress bar with a no-op context manager
    class DummyBar:
        def __init__(self, *_: Any, **__: Any) -> None: ...
        def __enter__(self) -> Any:
            return lambda: None

        def __exit__(self, *_: object) -> None:
            return None

    # Use a monotonic counter for perf_counter to avoid zero elapsed time
    t = {"v": 0.0}

    def fake_perf_counter() -> float:
        t["v"] += 0.01
        return t["v"]

    captured: dict[str, Any] = {}

    def fake_write(file_path: Path, output_data: list[dict[str, Any]]) -> None:
        captured["data"] = output_data

    with (
        patch("latency_test.alive_bar", DummyBar),
        patch("latency_test.time.sleep", lambda _x: None),
        patch("latency_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.sleep", lambda _x: None),
        patch.object(LatencyTest, "_write_output_to_file", side_effect=fake_write),
    ):
        tester.main_test(
            num_times=2,
            samples=3,
            min_wait=0.0,
            max_wait=0.0,
            wait_time=0.0,
            jitter=False,
            length=6,
        )

    # Validate structure of written data
    assert "data" in captured
    out = captured["data"]
    assert isinstance(out, list)
    assert len(out) == 2
    for item in out:
        assert item["samples"] == 3
        assert item["latency_avg"] == 0
        assert item["latency_min"] == 0
        assert item["latency_max"] == 0
        assert item["latency_p95"] == 0
        assert item["dropped_messages"] == 3
        assert isinstance(item["bitrate"], float)
        assert item["results"] == []
        assert item["outstanding_messages"] == [1, 2, 3]
        assert item["outstanding_max"] == 3
        assert item["outstanding_final"] == 3
        assert "status_before" in item
        assert "status_after" in item
        assert "status_delta" in item
        assert "statistics" in item["status_before"]
        assert "tasks" in item["status_before"]
        assert "received" in item["status_before"]
        assert "complete" in item["status_before"]


def test_main_test_with_jitter_path() -> None:
    """main_test with jitter=True exercises the random.uniform sleep path."""
    mock_ser = Mock(spec=SerialInterface)
    mock_ser.baudrate = 115200
    tester = LatencyTest(mock_ser)

    class DummyBar:
        def __init__(self, *_: Any, **__: Any) -> None: ...
        def __enter__(self) -> Any:
            return lambda: None

        def __exit__(self, *_: object) -> None:
            return None

    t = {"v": 0.0}

    def fake_perf_counter() -> float:
        t["v"] += 0.01
        return t["v"]

    with (
        patch("latency_test.alive_bar", DummyBar),
        patch("latency_test.time.sleep", lambda _x: None),
        patch("latency_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.sleep", lambda _x: None),
        patch("latency_test.random.uniform", return_value=0.0),
        patch.object(LatencyTest, "_write_output_to_file"),
    ):
        tester.main_test(
            num_times=2,
            samples=2,
            min_wait=0.0,
            max_wait=0.1,
            wait_time=0.0,
            jitter=True,
            length=6,
        )
