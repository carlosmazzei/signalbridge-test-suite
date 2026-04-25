"""Unit tests for src/baud_rate_test.py."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import Mock, patch

from base_test import (
    DEFAULT_MESSAGE_LENGTH,
    DEFAULT_SAMPLES,
    DEFAULT_WAIT_TIME,
)
from baud_rate_test import (
    DEFAULT_BAUD_RATES,
    BaudRateTest,
)
from serial_interface import SerialInterface


def test_baud_rate_test_sweeps_rates_and_writes_output() -> None:
    """baud_rate_test iterates over baud rates, sets each, and writes results."""
    mock_ser = Mock(spec=SerialInterface)
    mock_ser.baudrate = 115200
    mock_ser.set_baudrate = Mock(return_value=True)
    mock_ser.set_message_handler = Mock()
    tester = BaudRateTest(mock_ser)

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

    captured: dict[str, Any] = {}

    def fake_write(_file_path: object, output_data: list[dict[str, Any]]) -> None:
        captured["data"] = output_data

    baud_rates = [9600, 115200]

    with (
        patch("baud_rate_test.alive_bar", DummyBar),
        patch("baud_rate_test.time.sleep", lambda _x: None),
        patch("baud_rate_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.sleep", lambda _x: None),
        patch.object(BaudRateTest, "_write_output_to_file", side_effect=fake_write),
    ):
        tester.baud_rate_test(
            baud_rates=baud_rates,
            samples=3,
            wait_time=0.0,
            length=6,
        )

    assert mock_ser.set_baudrate.call_count == len(baud_rates) + 1

    assert "data" in captured
    out = captured["data"]
    assert len(out) == len(baud_rates)
    for i, item in enumerate(out):
        assert item["baudrate"] == baud_rates[i]
        assert item["samples"] == 3
        assert isinstance(item["bitrate"], float)
        assert "results" in item
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


def test_baud_rate_test_skips_failed_baudrate() -> None:
    """baud_rate_test skips rates where set_baudrate fails."""
    mock_ser = Mock(spec=SerialInterface)
    mock_ser.baudrate = 115200
    mock_ser.set_baudrate = Mock(side_effect=[False, True, True])
    mock_ser.set_message_handler = Mock()
    tester = BaudRateTest(mock_ser)

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

    captured: dict[str, Any] = {}

    def fake_write(_file_path: object, output_data: list[dict[str, Any]]) -> None:
        captured["data"] = output_data

    with (
        patch("baud_rate_test.alive_bar", DummyBar),
        patch("baud_rate_test.time.sleep", lambda _x: None),
        patch("baud_rate_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.sleep", lambda _x: None),
        patch.object(BaudRateTest, "_write_output_to_file", side_effect=fake_write),
    ):
        tester.baud_rate_test(
            baud_rates=[9600, 115200],
            samples=2,
            wait_time=0.0,
            length=6,
        )

    out = captured["data"]
    assert len(out) == 1
    assert out[0]["baudrate"] == 115200
    assert out[0]["outstanding_messages"] == [1, 2]
    assert out[0]["outstanding_max"] == 2
    assert out[0]["outstanding_final"] == 2
    assert "status_before" in out[0]
    assert "status_after" in out[0]
    assert "status_delta" in out[0]


def test_show_baud_options_defaults() -> None:
    """_show_baud_options returns defaults when user accepts them."""
    tester = BaudRateTest(Mock(spec=SerialInterface))
    with patch.object(
        BaudRateTest,
        "_get_user_input",
        side_effect=[True, DEFAULT_SAMPLES, DEFAULT_WAIT_TIME, DEFAULT_MESSAGE_LENGTH],
    ):
        baud_rates, samples, wait_time, length = tester._show_baud_options()
    assert baud_rates == DEFAULT_BAUD_RATES
    assert samples == DEFAULT_SAMPLES
    assert wait_time == DEFAULT_WAIT_TIME
    assert length == DEFAULT_MESSAGE_LENGTH


def test_execute_baud_test_no_serial(caplog: Any) -> None:
    """execute_baud_test exits early when no serial interface is provided."""
    tester = BaudRateTest(ser=None)  # type: ignore[arg-type]
    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("baud_rate_test")
        logger.addHandler(caplog.handler)
        tester.execute_baud_test()
        logger.removeHandler(caplog.handler)
    assert "No serial port found. Quitting test." in caplog.text


class TestShowBaudOptionsCustom:
    """Tests for _show_baud_options with custom baud rates."""

    def test_custom_baud_rates(self) -> None:
        """_show_baud_options returns custom baud rates when user provides them."""
        tester = BaudRateTest(Mock(spec=SerialInterface))
        with (
            patch.object(
                BaudRateTest,
                "_get_user_input",
                side_effect=[
                    False,
                    DEFAULT_SAMPLES,
                    DEFAULT_WAIT_TIME,
                    DEFAULT_MESSAGE_LENGTH,
                ],
            ),
            patch("baud_rate_test.console") as mock_console,
        ):
            mock_console.input.return_value = "9600,115200"
            baud_rates, samples, wait_time, length = tester._show_baud_options()
        assert baud_rates == [9600, 115200]
        assert samples == DEFAULT_SAMPLES
        assert wait_time == DEFAULT_WAIT_TIME
        assert length == DEFAULT_MESSAGE_LENGTH


def test_invalid_num_samples_zero() -> None:
    """_show_baud_options resets num_samples to default when zero."""
    tester = BaudRateTest(Mock(spec=SerialInterface))
    with patch.object(
        BaudRateTest,
        "_get_user_input",
        side_effect=[True, 0, DEFAULT_WAIT_TIME, DEFAULT_MESSAGE_LENGTH],
    ):
        baud_rates, samples, wait_time, length = tester._show_baud_options()
    assert baud_rates == DEFAULT_BAUD_RATES
    assert samples == DEFAULT_SAMPLES
    assert wait_time == DEFAULT_WAIT_TIME
    assert length == DEFAULT_MESSAGE_LENGTH


def test_invalid_wait_time_negative() -> None:
    """_show_baud_options resets wait_time to default when negative."""
    tester = BaudRateTest(Mock(spec=SerialInterface))
    with patch.object(
        BaudRateTest,
        "_get_user_input",
        side_effect=[True, DEFAULT_SAMPLES, -1, DEFAULT_MESSAGE_LENGTH],
    ):
        baud_rates, samples, wait_time, length = tester._show_baud_options()
    assert baud_rates == DEFAULT_BAUD_RATES
    assert samples == DEFAULT_SAMPLES
    assert wait_time == DEFAULT_WAIT_TIME
    assert length == DEFAULT_MESSAGE_LENGTH


def test_invalid_message_length_5() -> None:
    """_show_baud_options resets message_length to default when below 6."""
    tester = BaudRateTest(Mock(spec=SerialInterface))
    with patch.object(
        BaudRateTest,
        "_get_user_input",
        side_effect=[True, DEFAULT_SAMPLES, DEFAULT_WAIT_TIME, 5],
    ):
        baud_rates, samples, wait_time, length = tester._show_baud_options()
    assert baud_rates == DEFAULT_BAUD_RATES
    assert samples == DEFAULT_SAMPLES
    assert wait_time == DEFAULT_WAIT_TIME
    assert length == DEFAULT_MESSAGE_LENGTH


def test_invalid_message_length_11() -> None:
    """_show_baud_options resets message_length to default when above 10."""
    tester = BaudRateTest(Mock(spec=SerialInterface))
    with patch.object(
        BaudRateTest,
        "_get_user_input",
        side_effect=[True, DEFAULT_SAMPLES, DEFAULT_WAIT_TIME, 11],
    ):
        baud_rates, samples, wait_time, length = tester._show_baud_options()
    assert baud_rates == DEFAULT_BAUD_RATES
    assert samples == DEFAULT_SAMPLES
    assert wait_time == DEFAULT_WAIT_TIME
    assert length == DEFAULT_MESSAGE_LENGTH


def test_baud_rate_test_no_restore() -> None:
    """baud_rate_test does not restore original baudrate when restore_baudrate=False."""
    mock_ser = Mock(spec=SerialInterface)
    mock_ser.baudrate = 115200
    mock_ser.set_baudrate = Mock(return_value=True)
    mock_ser.set_message_handler = Mock()
    tester = BaudRateTest(mock_ser)

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
        patch("baud_rate_test.alive_bar", DummyBar),
        patch("baud_rate_test.time.sleep", lambda _x: None),
        patch("baud_rate_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.perf_counter", side_effect=fake_perf_counter),
        patch("base_test.time.sleep", lambda _x: None),
        patch.object(BaudRateTest, "_write_output_to_file", Mock()),
    ):
        tester.baud_rate_test(
            baud_rates=[9600],
            samples=2,
            wait_time=0.0,
            length=6,
            restore_baudrate=False,
        )

    # set_baudrate should only be called once (for setting 9600), NOT a second
    # time for restoring the original 115200 baudrate.
    assert mock_ser.set_baudrate.call_count == 1
    mock_ser.set_baudrate.assert_called_once_with(9600)


def test_execute_baud_test_normal() -> None:
    """execute_baud_test calls baud_rate_test with the options returned by _show_baud_options."""
    mock_ser = Mock(spec=SerialInterface)
    tester = BaudRateTest(mock_ser)

    with (
        patch.object(
            BaudRateTest,
            "_show_baud_options",
            return_value=([9600, 115200], 10, 1.0, 8),
        ),
        patch.object(BaudRateTest, "baud_rate_test") as mock_baud_test,
        patch("baud_rate_test.time.sleep", lambda _x: None),
    ):
        tester.execute_baud_test()

    mock_baud_test.assert_called_once_with(
        baud_rates=[9600, 115200],
        samples=10,
        wait_time=1.0,
        length=8,
    )


def test_execute_baud_test_keyboard_interrupt() -> None:
    """execute_baud_test handles KeyboardInterrupt gracefully."""
    mock_ser = Mock(spec=SerialInterface)
    tester = BaudRateTest(mock_ser)

    with (
        patch.object(
            BaudRateTest,
            "_show_baud_options",
            side_effect=KeyboardInterrupt,
        ),
        patch("baud_rate_test.time.sleep", lambda _x: None),
    ):
        # Should not raise; the function catches KeyboardInterrupt internally
        tester.execute_baud_test()


def test_execute_baud_test_with_options_calls_baud_rate_test() -> None:
    """execute_baud_test_with_options delegates to baud_rate_test."""
    tester = BaudRateTest(Mock(spec=SerialInterface))
    with patch.object(tester, "baud_rate_test") as mock_sweep:
        tester.execute_baud_test_with_options(
            baud_rates=[9600, 115200],
            samples=12,
            wait_time=0.2,
            length=8,
        )
    mock_sweep.assert_called_once_with(
        baud_rates=[9600, 115200],
        samples=12,
        wait_time=0.2,
        length=8,
    )
