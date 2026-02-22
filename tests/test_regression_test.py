"""Tests for RegressionTest module."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from regression_test import RegressionTest
from serial_interface import SerialCommand, SerialInterface


@pytest.fixture
def mock_serial() -> Mock:
    """Fixture for a mocked SerialInterface."""
    return Mock(spec=SerialInterface)


@pytest.fixture
def regression_test(mock_serial: Mock) -> RegressionTest:
    """Fixture for RegressionTest with a mocked serial interface."""
    return RegressionTest(mock_serial)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------
class TestRegressionTestInit:
    """Tests for RegressionTest.__init__."""

    def test_ser_attribute_stored(
        self, regression_test: RegressionTest, mock_serial: Mock
    ) -> None:
        """Ser should be stored upon construction."""
        assert regression_test.ser is mock_serial

    def test_logger_attribute_set(self, regression_test: RegressionTest) -> None:
        """Logger attribute should be set upon construction."""
        assert regression_test.logger is not None


# ---------------------------------------------------------------------------
# handle_message — ECHO_COMMAND
# ---------------------------------------------------------------------------
class TestHandleMessage:
    """Tests for RegressionTest.handle_message."""

    EXPECTED_ECHO = bytes([0x00, 0x34, 0x02, 0x01, 0x02])

    def test_matching_echo_logs_ok(self, regression_test: RegressionTest) -> None:
        """Correct echo payload should call logger.info with '[OK] Echo command'."""
        logged: list[str] = []
        with patch("regression_test.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(
                msg % args if args else msg
            )
            regression_test.handle_message(
                SerialCommand.ECHO_COMMAND.value,
                self.EXPECTED_ECHO,
                b"raw",
            )
        assert any("[OK] Echo command" in m for m in logged)

    def test_wrong_echo_logs_fail(self, regression_test: RegressionTest) -> None:
        """Incorrect echo payload should call logger.info with '[FAIL] Echo command'."""
        wrong_data = bytes([0x00, 0x34, 0x02, 0x01, 0xFF])
        logged: list[str] = []
        with patch("regression_test.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(
                msg % args if args else msg
            )
            regression_test.handle_message(
                SerialCommand.ECHO_COMMAND.value,
                wrong_data,
                b"raw",
            )
        assert any("[FAIL] Echo command" in m for m in logged)

    def test_echo_logs_expected_bytes(self, regression_test: RegressionTest) -> None:
        """handle_message should log the expected bytes value."""
        logged: list[str] = []
        with patch("regression_test.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(
                msg % args if args else msg
            )
            regression_test.handle_message(
                SerialCommand.ECHO_COMMAND.value,
                self.EXPECTED_ECHO,
                b"raw",
            )
        assert any("Expected:" in m for m in logged)

    def test_non_echo_command_does_nothing(
        self, regression_test: RegressionTest
    ) -> None:
        """Non-ECHO_COMMAND messages should not trigger any logging."""
        with patch("regression_test.logger") as mock_log:
            regression_test.handle_message(
                SerialCommand.KEY_COMMAND.value,
                b"irrelevant",
                b"raw",
            )
        mock_log.info.assert_not_called()

    def test_short_data_does_not_raise(self, regression_test: RegressionTest) -> None:
        """IndexError from short decoded_data should be caught without raising."""
        # Empty bytes will trigger IndexError in the equality check
        regression_test.handle_message(SerialCommand.ECHO_COMMAND.value, b"", b"raw")

    def test_echo_logs_received_and_command(
        self, regression_test: RegressionTest
    ) -> None:
        """handle_message should log received bytes, command and decoded data."""
        logged: list[str] = []
        with patch("regression_test.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(
                msg % args if args else msg
            )
            regression_test.handle_message(
                SerialCommand.ECHO_COMMAND.value,
                self.EXPECTED_ECHO,
                b"raw_bytes",
            )
        combined = " ".join(logged)
        assert "Received:" in combined
        assert "Test ended" in combined


# ---------------------------------------------------------------------------
# test_echo_command
# ---------------------------------------------------------------------------
class TestTestEchoCommand:
    """Tests for RegressionTest.test_echo_command."""

    EXPECTED_PAYLOAD = bytes([0x00, 0x34, 0x02, 0x01, 0x02])

    def test_writes_expected_payload(
        self, regression_test: RegressionTest, mock_serial: Mock
    ) -> None:
        """test_echo_command must call ser.write with the exact echo payload."""
        regression_test.test_echo_command()
        mock_serial.write.assert_called_once_with(self.EXPECTED_PAYLOAD)


# ---------------------------------------------------------------------------
# execute_test
# ---------------------------------------------------------------------------
class TestExecuteTest:
    """Tests for RegressionTest.execute_test."""

    def test_calls_test_echo_command(self, regression_test: RegressionTest) -> None:
        """execute_test must delegate to test_echo_command."""
        with patch.object(regression_test, "test_echo_command") as mock_echo:
            regression_test.execute_test()
        mock_echo.assert_called_once()
