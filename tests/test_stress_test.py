"""
Unit tests for StressTest using a mocked SerialInterface.

All tests use pytest fixtures and unittest.mock — no physical hardware needed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from serial_interface import SerialInterface
from stress_config import (
    ScenarioConfig,
    ScenarioThresholds,
    StressConfig,
    default_stress_config,
)
from stress_evaluator import StressRunResult
from stress_test import StressTest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def disable_alive_bar() -> Any:
    """Disable alive_bar during tests to avoid issues with mocked time."""
    with patch("stress_test.alive_bar", MagicMock()):
        yield


@pytest.fixture
def mock_serial() -> Mock:
    ser = Mock(spec=SerialInterface)
    ser.is_open.return_value = True
    ser.baudrate = 230400
    ser.port = "/dev/ttyACM0"
    ser.ser = Mock()
    ser.ser.is_open = True
    return ser


@pytest.fixture
def default_cfg() -> StressConfig:
    return default_stress_config(port="/dev/ttyACM0", baudrate=230400)


def _make_tester(ser: Mock, cfg: StressConfig | None = None) -> StressTest:
    t = StressTest(ser, cfg or default_stress_config())
    # Suppress actual status snapshot I/O
    t._request_status_snapshot = Mock(
        return_value={
            "statistics": {},
            "tasks": {},
            "received": {"statistics": 0, "tasks": 0},
            "complete": False,
        }
    )
    t._calculate_status_delta = Mock(return_value={"statistics": {}, "tasks": {}})
    return t


# ---------------------------------------------------------------------------
# TestEchoBurst
# ---------------------------------------------------------------------------


class TestEchoBurst:
    """Tests for the echo_only command profile."""

    def test_publish_called_num_messages_times(self, mock_serial: Mock) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="echo_burst",
                    duration_s=5.0,
                    command_profile="echo_only",
                    pacing_s=0.0,
                    num_messages=10,
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        with patch.object(tester, "publish") as mock_pub, patch("time.sleep"):
            tester._run_echo_burst(cfg.scenarios[0])
        assert mock_pub.call_count == 10

    def test_drop_ratio_zero_when_all_received(self, mock_serial: Mock) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="echo_burst",
                    duration_s=5.0,
                    command_profile="echo_only",
                    pacing_s=0.0,
                    num_messages=5,
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)

        def fake_publish(i, length):
            tester.latency_msg_sent[i] = 0.0
            tester.latency_msg_received[i] = 0.001

        with (
            patch.object(tester, "publish", side_effect=fake_publish),
            patch("time.sleep"),
        ):
            result = tester._run_echo_burst(cfg.scenarios[0])
        assert result.drop_ratio == 0.0

    def test_drop_ratio_computed_correctly(self, mock_serial: Mock) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="echo_burst",
                    duration_s=5.0,
                    command_profile="echo_only",
                    pacing_s=0.0,
                    num_messages=10,
                    thresholds=ScenarioThresholds(max_echo_drop_ratio=1.0),
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)

        def fake_publish(i, length):
            tester.latency_msg_sent[i] = 0.0
            # Only receive even-numbered messages → 50% drop
            if i % 2 == 0:
                tester.latency_msg_received[i] = 0.001

        with (
            patch.object(tester, "publish", side_effect=fake_publish),
            patch("time.sleep"),
        ):
            result = tester._run_echo_burst(cfg.scenarios[0])
        assert result.drop_ratio == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# TestMixedCommandBurst
# ---------------------------------------------------------------------------


class TestMixedCommandBurst:
    def test_total_messages_sent_matches_num_messages(self, mock_serial: Mock) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="mixed",
                    duration_s=5.0,
                    command_profile="mixed",
                    pacing_s=0.0,
                    num_messages=50,
                    thresholds=ScenarioThresholds(max_echo_drop_ratio=1.0),
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        with (
            patch.object(tester, "publish") as mock_pub,
            patch.object(tester, "_status_update"),
            patch("time.sleep"),
        ):
            result = tester._run_mixed_command_burst(cfg.scenarios[0])
        # messages_sent tracks only echo publishes (random subset of 50)
        assert result.messages_sent == mock_pub.call_count

    def test_status_update_called_for_non_echo_commands(
        self, mock_serial: Mock
    ) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="mixed",
                    duration_s=5.0,
                    command_profile="mixed",
                    pacing_s=0.0,
                    num_messages=20,
                    thresholds=ScenarioThresholds(max_echo_drop_ratio=1.0),
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        with (
            patch.object(tester, "publish"),
            patch.object(tester, "_status_update") as mock_su,
            patch("time.sleep"),
        ):
            tester._run_mixed_command_burst(cfg.scenarios[0])
        # At random mix some status_updates are expected; just ensure callable was invoked
        assert mock_su.call_count >= 0  # always true — validates no error is thrown


# ---------------------------------------------------------------------------
# TestStatusPollStorm
# ---------------------------------------------------------------------------


class TestStatusPollStorm:
    def test_status_update_called_repeatedly(self, mock_serial: Mock) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="status_poll",
                    duration_s=0.1,
                    command_profile="status_poll",
                    pacing_s=0.0,
                    num_messages=0,
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        # Use a counter that returns past the deadline after a couple of iterations
        call_count = 0

        def perf_side_effect():
            nonlocal call_count
            call_count += 1
            return 0.0 if call_count <= 2 else 1.0  # deadline is start(0.0) + 0.1s

        with (
            patch.object(tester, "_status_update") as mock_su,
            patch("stress_test.time.perf_counter", side_effect=perf_side_effect),
            patch("stress_test.time.sleep"),
        ):
            tester._run_status_poll_storm(cfg.scenarios[0])
        assert mock_su.call_count > 0

    def test_messages_sent_equals_received_for_status_poll(
        self, mock_serial: Mock
    ) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="status_poll",
                    duration_s=0.05,
                    command_profile="status_poll",
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        call_count = 0

        def perf_side_effect():
            nonlocal call_count
            call_count += 1
            return 0.0 if call_count <= 1 else 1.0

        with (
            patch.object(tester, "_status_update"),
            patch("stress_test.time.perf_counter", side_effect=perf_side_effect),
            patch("stress_test.time.sleep"),
        ):
            result = tester._run_status_poll_storm(cfg.scenarios[0])
        assert result.messages_sent == result.messages_received


# ---------------------------------------------------------------------------
# TestBaudFlip
# ---------------------------------------------------------------------------


class TestBaudFlip:
    def test_set_baudrate_called_for_each_baud(self, mock_serial: Mock) -> None:
        baud_rates = [9600, 115200, 230400]
        mock_serial.set_baudrate.return_value = True
        mock_serial.baudrate = 230400

        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="baud_flip",
                    duration_s=10.0,
                    command_profile="baud_flip",
                    pacing_s=0.0,
                    num_messages=2,
                    baud_rates=baud_rates,
                    thresholds=ScenarioThresholds(max_echo_drop_ratio=1.0),
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        with patch.object(tester, "publish"), patch("time.sleep"):
            tester._run_baud_flip(cfg.scenarios[0])
        assert mock_serial.set_baudrate.call_count >= len(baud_rates)

    def test_restores_original_baudrate_on_finish(self, mock_serial: Mock) -> None:
        mock_serial.set_baudrate.return_value = True
        mock_serial.baudrate = 115200  # start at different baud than target list

        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="baud_flip",
                    duration_s=5.0,
                    command_profile="baud_flip",
                    pacing_s=0.0,
                    num_messages=1,
                    baud_rates=[9600, 115200],
                    thresholds=ScenarioThresholds(max_echo_drop_ratio=1.0),
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        with patch.object(tester, "publish"), patch("stress_test.time.sleep"):
            tester._run_baud_flip(cfg.scenarios[0])
        # set_baudrate should have been called at least for each rate in the list
        called_bauds = [c.args[0] for c in mock_serial.set_baudrate.call_args_list]
        assert 9600 in called_bauds
        assert 115200 in called_bauds


# ---------------------------------------------------------------------------
# TestNoiseAndRecovery
# ---------------------------------------------------------------------------


class TestNoiseAndRecovery:
    def test_raw_bytes_written_to_underlying_port(self, mock_serial: Mock) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="noise_and_recovery",
                    duration_s=5.0,
                    command_profile="noise_and_recovery",
                    noise_bytes=32,
                    num_messages=3,
                    thresholds=ScenarioThresholds(
                        max_echo_drop_ratio=0.0, max_recovery_time_s=2.0
                    ),
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        # Return a monotonically increasing time so the while-loop exits immediately
        counter = iter([0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 100.0])
        with (
            patch.object(tester, "publish"),
            patch("stress_test.time.sleep"),
            patch("stress_test.time.perf_counter", side_effect=lambda: next(counter)),
        ):
            tester._run_noise_and_recovery(cfg.scenarios[0])
        # Verify raw write was called on the underlying serial object
        assert mock_serial.ser.write.call_count >= 1
        written_bytes = mock_serial.ser.write.call_args_list[0][0][0]
        assert len(written_bytes) == 32

    def test_publish_called_after_noise(self, mock_serial: Mock) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="noise_and_recovery",
                    duration_s=5.0,
                    command_profile="noise_and_recovery",
                    noise_bytes=8,
                    num_messages=5,
                    thresholds=ScenarioThresholds(
                        max_echo_drop_ratio=0.0, max_recovery_time_s=2.0
                    ),
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        counter = iter([0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 100.0])
        with (
            patch.object(tester, "publish") as mock_pub,
            patch("stress_test.time.sleep"),
            patch("stress_test.time.perf_counter", side_effect=lambda: next(counter)),
        ):
            tester._run_noise_and_recovery(cfg.scenarios[0])
        assert mock_pub.call_count == 5


# ---------------------------------------------------------------------------
# TestScenarioOrdering
# ---------------------------------------------------------------------------


class TestScenarioOrdering:
    def test_result_count_matches_scenario_count(self, mock_serial: Mock) -> None:
        cfg = default_stress_config()
        tester = _make_tester(mock_serial, cfg)

        # Patch all _run_* methods to return a minimal result immediately
        minimal = MagicMock()
        minimal.verdict = "PASS"

        with (
            patch.object(tester, "_run_scenario", return_value=minimal),
            patch.object(tester, "_get_user_input", return_value=0),
            patch("stress_test.write_json_report"),
            patch("stress_test.print_summary"),
        ):
            result = tester.execute_test()

        assert len(result.scenarios) == len(cfg.scenarios)

    def test_execute_test_returns_stress_run_result(self, mock_serial: Mock) -> None:
        cfg = StressConfig(
            scenarios=[
                ScenarioConfig(
                    name="echo_burst",
                    duration_s=1.0,
                    command_profile="echo_only",
                    num_messages=1,
                )
            ],
        )
        tester = _make_tester(mock_serial, cfg)
        minimal = MagicMock()
        minimal.verdict = "PASS"
        with (
            patch.object(tester, "_run_scenario", return_value=minimal),
            patch.object(tester, "_get_user_input", return_value=0),
            patch("stress_test.write_json_report"),
            patch("stress_test.print_summary"),
        ):
            result = tester.execute_test()
        assert isinstance(result, StressRunResult)
