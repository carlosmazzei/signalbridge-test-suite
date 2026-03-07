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

    def test_not_open_shows_panel(self) -> None:
        """When serial is closed, execute_command_mode should show a Rich panel."""
        ser = Mock(spec=SerialInterface)
        ser.is_open.return_value = False
        cm = CommandMode(ser)
        with patch("command_mode.console.print") as mock_console_print:
            cm.execute_command_mode()
        mock_console_print.assert_called_once()
        panel = mock_console_print.call_args[0][0]
        assert "not connected" in str(panel.renderable).lower()

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


# ---------------------------------------------------------------------------
# _print_prompt
# ---------------------------------------------------------------------------
class TestPrintPrompt:
    """Direct tests for CommandMode._print_prompt."""

    def test_stdout_write_called_with_prompt(self, command_mode: CommandMode) -> None:
        """sys.stdout.write should be called with self.prompt."""
        with patch("sys.stdout") as mock_stdout:
            command_mode._print_prompt()
        mock_stdout.write.assert_called_once_with(command_mode.prompt)

    def test_stdout_flush_called(self, command_mode: CommandMode) -> None:
        """sys.stdout.flush() should be called after writing prompt."""
        with patch("sys.stdout") as mock_stdout:
            command_mode._print_prompt()
        mock_stdout.flush.assert_called_once()

    def test_input_lock_acquired(self, command_mode: CommandMode) -> None:
        """input_lock should be acquired during _print_prompt."""
        mock_lock = Mock()
        mock_lock.__enter__ = Mock(return_value=None)
        mock_lock.__exit__ = Mock(return_value=False)
        command_mode.input_lock = mock_lock
        with patch("sys.stdout"):
            command_mode._print_prompt()
        mock_lock.__enter__.assert_called_once()
        mock_lock.__exit__.assert_called_once()


# ---------------------------------------------------------------------------
# _get_input
# ---------------------------------------------------------------------------
class TestGetInput:
    """Direct tests for CommandMode._get_input."""

    def test_character_accumulation(self, command_mode: CommandMode) -> None:
        """Characters should accumulate and be returned on newline."""
        command_mode.running = True
        with (
            patch("sys.stdin") as mock_stdin,
            patch("sys.stdout"),
        ):
            mock_stdin.read.side_effect = ["a", "b", "c", "\n"]
            result = command_mode._get_input()
        assert result == "abc"

    def test_backspace_removes_character(self, command_mode: CommandMode) -> None:
        r"""Backspace (\x7f) should remove last char and write '\b \b'."""
        command_mode.running = True
        with (
            patch("sys.stdin") as mock_stdin,
            patch("sys.stdout") as mock_stdout,
        ):
            mock_stdin.read.side_effect = ["a", "b", "\x7f", "\n"]
            result = command_mode._get_input()
        assert result == "a"
        mock_stdout.write.assert_any_call("\b \b")

    def test_empty_return_when_not_running(self, command_mode: CommandMode) -> None:
        """When running=False, _get_input should return empty string."""
        command_mode.running = False
        result = command_mode._get_input()
        assert result == ""


# ---------------------------------------------------------------------------
# _print_decoded_message — value verification
# ---------------------------------------------------------------------------
class TestPrintDecodedMessageValues:
    """Tests verifying exact computed values in _print_decoded_message."""

    def test_key_command_exact_values(self, command_mode: CommandMode) -> None:
        """KEY_COMMAND should log exact rxid, command, col, row, state values."""
        key_cmd = SerialCommand.KEY_COMMAND.value  # 4
        # Construct message bytes with known values:
        # rxid = (message[0] << 3) | ((message[1] & 0xE0) >> 5)
        # We want rxid=5: message[0]=0, then (0xE0 >> 5) = 0b101 = 5
        #   message[1] = 0xE0 | (key_cmd & 0x1F) = 0xE0 | 0x04 = 0xE4
        # command = message[1] & 0x1F = 0x04 = 4
        # length = message[2] = 0x04
        # message[3] = state(bit0) | row(bits 1-4) | col(bits 4-7)
        #   state=1 (bit0=1), row=3 (bits 1-4 = 0b0011 << 1 = 0x06),
        #   col=2 (bits 4-7 = 0b0010 << 4 = 0x20)
        #   message[3] = 0x20 | 0x06 | 0x01 = 0x27
        byte0 = 0x00
        byte1 = 0xE4  # rxid high bits=0b111=7*... let's recompute
        # rxid = (0x00 << 3) | ((0xE4 & 0xE0) >> 5) = 0 | (0xE0 >> 5) = 0 | 7 = 7
        # command = 0xE4 & 0x1F = 4
        byte2 = 0x04  # length
        # state=1, row=3, col=2
        # message[3] = (col << 4) | (row << 1) | state = (2<<4)|(3<<1)|1 = 32|6|1 = 39 = 0x27
        byte3 = 0x27
        data = bytes([byte0, byte1, byte2, byte3])

        logged: list[str] = []
        with patch("command_mode.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(msg % args)
            command_mode._print_decoded_message(data)

        combined = " ".join(logged)
        # rxid = 7, command = 4
        assert "Id: 7" in combined
        assert "Command: 4" in combined
        # col=2, row=3, state=1, length=4
        assert "Column: 2" in combined
        assert "Row: 3" in combined
        assert "State: 1" in combined
        assert "Length: 4" in combined

    def test_analog_command_exact_values(self, command_mode: CommandMode) -> None:
        """ANALOG_COMMAND should log exact channel and value."""
        analog_cmd = SerialCommand.ANALOG_COMMAND.value  # 3
        # channel = message[3] = 5
        # value = (message[4] << 8) | message[5] = (0x02 << 8) | 0x8A = 650
        byte0 = 0x00
        byte1 = analog_cmd & 0x1F  # 0x03
        byte2 = 0x03  # length
        byte3 = 0x05  # channel = 5
        byte4 = 0x02  # value high byte
        byte5 = 0x8A  # value low byte -> value = 0x028A = 650
        data = bytes([byte0, byte1, byte2, byte3, byte4, byte5])

        logged: list[str] = []
        with patch("command_mode.logger") as mock_log:
            mock_log.info.side_effect = lambda msg, *args: logged.append(msg % args)
            command_mode._print_decoded_message(data)

        combined = " ".join(logged)
        assert "Channel: 5" in combined
        assert "Value: 650" in combined


# ---------------------------------------------------------------------------
# execute_command_mode — additional scenarios
# ---------------------------------------------------------------------------
class TestExecuteCommandModeAdditional:
    """Additional tests for CommandMode.execute_command_mode."""

    def test_hex_data_sent_then_exit(self, command_mode: CommandMode) -> None:
        """Hex data should be sent via send_command, then 'x' exits."""
        call_count = [0]

        def fake_get_input() -> str:
            call_count[0] += 1
            if call_count[0] == 1:
                return "AA BB CC"
            return "x"

        with (
            patch.object(command_mode, "_print_prompt"),
            patch.object(command_mode, "_get_input", side_effect=fake_get_input),
            patch.object(command_mode, "_process_messages"),
        ):
            command_mode.execute_command_mode()

        command_mode.serial_interface.send_command.assert_called_once_with("AA BB CC")
        assert command_mode.running is False

    def test_keyboard_interrupt_exits_gracefully(
        self, command_mode: CommandMode
    ) -> None:
        """KeyboardInterrupt during _get_input should set running=False."""
        with (
            patch.object(command_mode, "_print_prompt"),
            patch.object(command_mode, "_get_input", side_effect=KeyboardInterrupt),
            patch.object(command_mode, "_process_messages"),
        ):
            command_mode.execute_command_mode()

        assert command_mode.running is False

    def test_uppercase_x_exits(self, command_mode: CommandMode) -> None:
        """Uppercase 'X' should also exit the loop (tests .lower() == 'x')."""
        with (
            patch.object(command_mode, "_print_prompt"),
            patch.object(command_mode, "_get_input", return_value="X"),
            patch.object(command_mode, "_process_messages"),
        ):
            command_mode.execute_command_mode()

        assert command_mode.running is False
