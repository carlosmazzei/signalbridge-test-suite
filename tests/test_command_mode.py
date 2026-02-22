"""Tests for CommandMode module."""

from __future__ import annotations

from io import StringIO
from unittest.mock import Mock, patch

import pytest

from command_mode import CommandMode
from serial_interface import SerialCommand, SerialInterface


@pytest.fixture
def mock_serial() -> Mock:
    """Fixture for a mocked SerialInterface."""
    ser = Mock(spec=SerialInterface)
    ser.is_open.return_value = True
    return ser


@pytest.fixture
def command_mode(mock_serial: Mock) -> CommandMode:
    """Fixture for CommandMode with a mocked serial interface."""
    return CommandMode(mock_serial)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------
class TestCommandModeInit:
    """Tests for CommandMode.__init__."""

    def test_serial_interface_stored(
        self, command_mode: CommandMode, mock_serial: Mock
    ) -> None:
        """serial_interface should be stored upon construction."""
        assert command_mode.serial_interface is mock_serial

    def test_message_queue_is_empty(self, command_mode: CommandMode) -> None:
        """message_queue should be empty on init."""
        assert command_mode.message_queue.empty()

    def test_running_starts_false(self, command_mode: CommandMode) -> None:
        """Running should be False on init."""
        assert command_mode.running is False

    def test_current_input_starts_empty(self, command_mode: CommandMode) -> None:
        """current_input should be empty string on init."""
        assert command_mode.current_input == ""

    def test_prompt_contains_expected_text(self, command_mode: CommandMode) -> None:
        """Prompt should contain exit instruction."""
        assert "x to exit" in command_mode.prompt.lower()


# ---------------------------------------------------------------------------
# handle_message
# ---------------------------------------------------------------------------
class TestHandleMessage:
    """Tests for CommandMode.handle_message."""

    def test_puts_message_in_queue(self, command_mode: CommandMode) -> None:
        """handle_message should enqueue the (command, data, bytes) tuple."""
        command_mode.handle_message(1, b"data", b"raw")
        assert not command_mode.message_queue.empty()
        item = command_mode.message_queue.get_nowait()
        assert item == (1, b"data", b"raw")

    def test_multiple_messages_queued_in_order(self, command_mode: CommandMode) -> None:
        """Multiple messages should be enqueued in FIFO order."""
        command_mode.handle_message(1, b"a", b"ra")
        command_mode.handle_message(2, b"b", b"rb")
        assert command_mode.message_queue.get_nowait() == (1, b"a", b"ra")
        assert command_mode.message_queue.get_nowait() == (2, b"b", b"rb")


# ---------------------------------------------------------------------------
# _handle_message — internal handler
# ---------------------------------------------------------------------------
class TestInternalHandleMessage:
    """Tests for CommandMode._handle_message."""

    def _valid_data(self, command_val: int) -> bytes:
        """Build a minimal decoded_data for the given command value."""
        # byte[1] holds (rxid << 5 | command); we want command low 5 bits
        byte1 = command_val & 0x1F
        return bytes([0x00, byte1, 0x01, 0x00, 0x00, 0x00])

    def test_analog_command_suppressed(self, command_mode: CommandMode) -> None:
        """ANALOG_COMMAND should NOT write to stdout or call _print_decoded_message."""
        with (
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch.object(command_mode, "_print_decoded_message") as mock_print,
            patch("command_mode.cobs.decode", return_value=b"\x00\x04\x01\x00\x00\x00"),
        ):
            command_mode._handle_message(
                SerialCommand.ANALOG_COMMAND.value,
                self._valid_data(SerialCommand.ANALOG_COMMAND.value),
                b"raw",
            )
        mock_print.assert_not_called()

    def test_non_analog_calls_print_decoded(self, command_mode: CommandMode) -> None:
        """Non-analog commands should call _print_decoded_message."""
        with (
            patch("sys.stdout", new_callable=StringIO),
            patch.object(command_mode, "_print_decoded_message") as mock_print,
            patch(
                "command_mode.cobs.decode",
                return_value=self._valid_data(SerialCommand.ECHO_COMMAND.value),
            ),
            patch("command_mode.calculate_checksum", return_value=b"\x00"),
        ):
            command_mode._handle_message(
                SerialCommand.ECHO_COMMAND.value,
                self._valid_data(SerialCommand.ECHO_COMMAND.value),
                b"raw",
            )
        mock_print.assert_called_once()


# ---------------------------------------------------------------------------
# _print_decoded_message
# ---------------------------------------------------------------------------
class TestPrintDecodedMessage:
    """Tests for CommandMode._print_decoded_message."""

    def test_key_command_logged(self, command_mode: CommandMode) -> None:
        """KEY_COMMAND data should log Column/Row/State."""
        key_cmd = SerialCommand.KEY_COMMAND.value
        data = bytes([0x00, key_cmd & 0x1F, 0x04, 0b0001_0011])
        logged: list[str] = []
        with patch("command_mode.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(msg % args)
            command_mode._print_decoded_message(data)
        combined = " ".join(logged)
        assert "Column:" in combined
        assert "Row:" in combined
        assert "State:" in combined

    def test_analog_command_logged(self, command_mode: CommandMode) -> None:
        """ANALOG_COMMAND data should log Channel/Value."""
        analog_cmd = SerialCommand.ANALOG_COMMAND.value
        data = bytes([0x00, analog_cmd & 0x1F, 0x03, 0x03, 0x01, 0x02])
        logged: list[str] = []
        with patch("command_mode.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(msg % args)
            command_mode._print_decoded_message(data)
        combined = " ".join(logged)
        assert "Channel:" in combined
        assert "Value:" in combined

    def test_decoded_message_logged(self, command_mode: CommandMode) -> None:
        """All messages should log a 'Decoded message:' entry."""
        data = bytes([0x00, 0x00, 0x01, 0x00, 0x00, 0x00])
        logged: list[str] = []
        with patch("command_mode.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(msg % args)
            command_mode._print_decoded_message(data)
        combined = " ".join(logged)
        assert "Decoded message:" in combined


# ---------------------------------------------------------------------------
# execute_command_mode
# ---------------------------------------------------------------------------
class TestExecuteCommandMode:
    """Tests for CommandMode.execute_command_mode."""

    def test_not_open_logs_message(self) -> None:
        """When serial is closed, execute_command_mode should log and return."""
        ser = Mock(spec=SerialInterface)
        ser.is_open.return_value = False
        cm = CommandMode(ser)
        logged: list[str] = []
        with patch("command_mode.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(
                msg % args if args else msg
            )
            cm.execute_command_mode()
        combined = " ".join(logged).lower()
        assert "not available" in combined or "not connected" in combined

    def test_x_input_exits_loop(self, command_mode: CommandMode) -> None:
        """Entering 'x' should set running=False and exit the loop."""
        with (
            patch.object(command_mode, "_print_prompt"),
            patch.object(command_mode, "_get_input", return_value="x"),
            patch.object(command_mode, "_process_messages"),
        ):
            command_mode.running = True
            command_mode.execute_command_mode()
        assert command_mode.running is False

    def test_starts_running_true(self, command_mode: Mock) -> None:
        """execute_command_mode should set running=True at start for open port."""
        events = []

        def capture_running(self_inner: CommandMode) -> str:
            events.append(self_inner.running)
            self_inner.running = False  # Force exit
            return "x"

        with (
            patch.object(command_mode, "_print_prompt"),
            patch.object(
                type(command_mode), "_get_input", lambda self: capture_running(self)
            ),
        ):
            command_mode.execute_command_mode()
        assert events[0] is True


# ---------------------------------------------------------------------------
# _process_messages
# ---------------------------------------------------------------------------
class TestProcessMessages:
    """Tests for CommandMode._process_messages."""

    def test_calls_handle_message_from_queue(self, command_mode: CommandMode) -> None:
        """_process_messages should dispatch queued messages to _handle_message."""

        def stop_after_one() -> None:
            command_mode.running = False

        command_mode.running = True
        command_mode.message_queue.put((1, b"data", b"raw"))

        with patch.object(command_mode, "_handle_message") as mock_handle:
            # Stop running after first message
            mock_handle.side_effect = lambda *_: stop_after_one()
            command_mode._process_messages()

        mock_handle.assert_called_once_with(1, b"data", b"raw")
