"""Unit test for application_manager.py."""

import importlib.util
import logging
import sys
import types
from collections.abc import Generator
from typing import Any
from unittest.mock import Mock, patch

import pytest


class _Dummy:
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - stub
        pass

    def open(self) -> bool:  # pragma: no cover - stub
        return True

    def close(self) -> None:  # pragma: no cover - stub
        return None

    def is_open(self) -> bool:  # pragma: no cover - stub
        return True

    def set_message_handler(self, _handler: Any) -> None:  # pragma: no cover - stub
        return None

    def start_reading(self) -> None:  # pragma: no cover - stub
        return None


def _dummy_func(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - stub
    return None


def _ensure_module(name: str, attrs: dict[str, Any]) -> None:
    if importlib.util.find_spec(name) is None:
        module = types.ModuleType(name)
        for attr_name, obj in attrs.items():
            setattr(module, attr_name, obj)
        sys.modules[name] = module


_ensure_module("command_mode", {"CommandMode": _Dummy})
_ensure_module("latency_test", {"LatencyTest": _Dummy})
_ensure_module("regression_test", {"RegressionTest": _Dummy})
_ensure_module("serial_interface", {"SerialInterface": _Dummy})
_ensure_module("status_mode", {"StatusMode": _Dummy})
_ensure_module("visualize_results", {"VisualizeResults": _Dummy})
_ensure_module("logger_config", {"setup_logging": _dummy_func})
_ensure_module(
    "const",
    {
        "TEST_RESULTS_FOLDER": "",
        "BAUDRATE": 0,
        "PORT_NAME": "",
        "TIMEOUT": 0,
    },
)

from application_manager import ApplicationManager, Mode  # noqa: E402
from serial_interface import SerialInterface  # noqa: E402


def _main_stub() -> None:  # pragma: no cover - stub
    import os

    from application_manager import ApplicationManager
    from const import BAUDRATE, PORT_NAME, TIMEOUT

    manager = ApplicationManager(PORT_NAME, BAUDRATE, TIMEOUT)
    os.system("clear")  # noqa: S605, S607
    manager.initialize()
    manager.run()


_ensure_module(
    "main",
    {
        "application_manager": sys.modules["application_manager"],
        "logger": logging.getLogger("main"),
        "main": _main_stub,
    },
)


@pytest.fixture
def mock_serial() -> Generator[Any, None, None]:
    """Fixture for mocked SerialInterface."""
    with patch("application_manager.SerialInterface") as mock:
        instance = Mock(spec=SerialInterface)
        mock.return_value = instance
        yield mock.return_value


@pytest.fixture
def app_manager(
    mock_serial: Generator[Any, None, None],
) -> ApplicationManager:
    """Fixture for ApplicationManager instance."""
    _ = mock_serial
    return ApplicationManager("COM1", 115200, 1.0)


def test_initialization(app_manager: ApplicationManager) -> None:
    """Test the initial state of ApplicationManager."""
    assert app_manager.mode == Mode.IDLE
    assert app_manager.available_modes == {Mode.VISUALIZE}
    assert app_manager.latency_test is None
    assert app_manager.regression_test is None
    assert app_manager.command_mode is None
    assert app_manager.visualize_results is None


def test_initialize_success(
    app_manager: ApplicationManager, mock_serial: SerialInterface
) -> None:
    """Test successful initialization."""
    mock_serial.open.return_value = True

    result = app_manager.initialize()

    assert result is True
    assert app_manager.latency_test is not None
    assert app_manager.command_mode is not None
    assert app_manager.visualize_results is not None
    assert app_manager.available_modes == {
        Mode.VISUALIZE,
        Mode.LATENCY,
        Mode.COMMAND,
        Mode.REGRESSION,
        Mode.STATUS,
    }
    mock_serial.set_message_handler.assert_called_once()
    mock_serial.start_reading.assert_called_once()
    app_manager.cleanup()


def test_initialize_failure(
    app_manager: ApplicationManager, mock_serial: SerialInterface
) -> None:
    """Test initialization when serial interface fails to open."""
    mock_serial.open.return_value = False
    result = app_manager.initialize()
    assert result is False
    assert app_manager.available_modes == {Mode.VISUALIZE}
    mock_serial.set_message_handler.assert_not_called()
    mock_serial.start_reading.assert_not_called()
    app_manager.cleanup()


def test_cleanup(app_manager: ApplicationManager, mock_serial: SerialInterface) -> None:
    """Test cleanup method."""
    app_manager.cleanup()
    mock_serial.close.assert_called_once()


def test_handle_message_latency_mode(app_manager: ApplicationManager) -> None:
    """Test message handling in latency mode."""
    # Setup
    app_manager.mode = Mode.LATENCY
    app_manager.latency_test = Mock()

    # Test
    command = 1
    decoded_data = b"test"
    byte_string = b"raw_test"
    app_manager.handle_message(command, decoded_data, byte_string)

    # Assert
    app_manager.latency_test.handle_message.assert_called_once_with(
        command, decoded_data
    )


def test_handle_message_command_mode(app_manager: ApplicationManager) -> None:
    """Test message handling in command mode."""
    # Setup
    app_manager.mode = Mode.COMMAND
    app_manager.command_mode = Mock()

    # Test
    command = 1
    decoded_data = b"test"
    byte_string = b"raw_test"
    app_manager.handle_message(command, decoded_data, byte_string)

    # Assert
    app_manager.command_mode.handle_message.assert_called_once_with(
        command, decoded_data, byte_string
    )


def test_handle_message_regression_mode(app_manager: ApplicationManager) -> None:
    """Test message handling in regression mode."""
    # Setup
    app_manager.mode = Mode.REGRESSION
    app_manager.regression_test = Mock()

    # Test
    command = 1
    decoded_data = b"test"
    byte_string = b"raw_test"
    app_manager.handle_message(command, decoded_data, byte_string)

    # Assert
    app_manager.regression_test.handle_message.assert_called_once_with(
        command, decoded_data, byte_string
    )


def test_run_latency_test_available(app_manager: ApplicationManager) -> None:
    """Test running latency test when available."""
    app_manager.latency_test = Mock()
    app_manager.available_modes.add(Mode.LATENCY)
    app_manager.run_latency_test()
    assert app_manager.mode == Mode.LATENCY
    app_manager.latency_test.execute_test.assert_called_once()


def test_run_latency_test_unavailable(app_manager: ApplicationManager) -> None:
    """Test running latency test when unavailable."""
    app_manager.latency_test = None
    app_manager.run_latency_test()
    assert app_manager.mode == Mode.IDLE


def test_run_command_mode_available(app_manager: ApplicationManager) -> None:
    """Test running command mode when available."""
    app_manager.command_mode = Mock()
    app_manager.available_modes.add(Mode.COMMAND)
    app_manager.run_command_mode()
    assert app_manager.mode == Mode.COMMAND
    app_manager.command_mode.execute_command_mode.assert_called_once()


def test_run_command_mode_unavailable(app_manager: ApplicationManager) -> None:
    """Test running command mode when unavailable."""
    app_manager.command_mode = None
    app_manager.run_command_mode()
    assert app_manager.mode == Mode.IDLE


def test_display_menu_all_modes(
    app_manager: ApplicationManager, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test display_menu with all modes available."""
    # Set up all modes as available
    app_manager.available_modes = {
        Mode.LATENCY,
        Mode.COMMAND,
        Mode.REGRESSION,
        Mode.VISUALIZE,
        Mode.STATUS,
    }
    app_manager.connected = True

    app_manager.display_menu()
    captured = capsys.readouterr()

    assert "Available options:" in captured.out
    assert "0. Disconnect from device" in captured.out
    assert "1. Run latency test" in captured.out
    assert "2. Send command" in captured.out
    assert "3. Regression test" in captured.out
    assert "4. Visualize test results" in captured.out
    assert "5. Status mode" in captured.out
    assert "6. Exit" in captured.out


def test_display_menu_no_modes(
    app_manager: ApplicationManager, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test display_menu with only visualization mode (default)."""
    # Default state only has VISUALIZE mode
    app_manager.available_modes = {Mode.VISUALIZE}

    app_manager.display_menu()
    captured = capsys.readouterr()

    assert "Available options:" in captured.out
    assert "0. Connect to device" in captured.out
    assert "1. Run latency test" not in captured.out
    assert "2. Send command" not in captured.out
    assert "3. Regression test" not in captured.out
    assert "4. Visualize test results" in captured.out
    assert "5. Status mode" not in captured.out
    assert "6. Exit" in captured.out


def test_display_menu_some_modes(
    app_manager: ApplicationManager, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test display_menu with a subset of modes available."""
    app_manager.available_modes = {Mode.LATENCY, Mode.VISUALIZE}
    app_manager.connected = True

    app_manager.display_menu()
    captured = capsys.readouterr()

    assert "Available options:" in captured.out
    assert "0. Disconnect from device" in captured.out
    assert "1. Run latency test" in captured.out
    assert "2. Send command" not in captured.out
    assert "3. Regression test" not in captured.out
    assert "4. Visualize test results" in captured.out
    assert "5. Status mode" not in captured.out
    assert "6. Exit" in captured.out


@pytest.mark.parametrize(
    ("choice", "mode", "expected_method"),
    [
        ("1", Mode.LATENCY, "run_latency_test"),
        ("2", Mode.COMMAND, "run_command_mode"),
        ("3", Mode.REGRESSION, "run_regression_test"),
        ("4", Mode.VISUALIZE, "run_visualization"),
        ("5", Mode.STATUS, "run_status_mode"),
    ],
)
def test_run_valid_choices(
    app_manager: ApplicationManager,
    choice: str,
    mode: Mode,
    expected_method: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test run method with valid menu choices."""
    # Setup available modes
    app_manager.available_modes.add(mode)

    # Mock the input and the expected method call
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", side_effect=[choice, "6"]),
        patch.object(app_manager, expected_method) as mock_method,
        patch.object(app_manager, "display_menu"),
        caplog.at_level(logging.INFO),
    ):
        logger.addHandler(caplog.handler)
        app_manager.run()
        logger.removeHandler(caplog.handler)

        # Verify the appropriate method was called
        mock_method.assert_called_once()
        assert "Exiting..." in caplog.text


def test_run_exit_choice(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Test run method with exit choice."""
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", return_value="6"),
        patch.object(app_manager, "display_menu"),
        caplog.at_level(logging.INFO),
    ):
        logger.addHandler(caplog.handler)
        app_manager.run()
        logger.removeHandler(caplog.handler)

        assert "Exiting..." in caplog.text


def test_run_invalid_choice(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Test run method with invalid choice."""
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", side_effect=["invalid", "6"]),
        patch.object(app_manager, "display_menu"),
        caplog.at_level(logging.INFO),
    ):
        logger.addHandler(caplog.handler)
        app_manager.run()
        logger.removeHandler(caplog.handler)

        assert "Invalid choice or option not available" in caplog.text
        assert "Exiting..." in caplog.text


def test_run_unavailable_mode(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Test run method with unavailable mode choice."""
    # Ensure LATENCY mode is not available
    app_manager.available_modes.discard(Mode.LATENCY)

    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", side_effect=["1", "6"]),
        patch.object(app_manager, "display_menu"),
        caplog.at_level(logging.INFO),
    ):
        logger.addHandler(caplog.handler)
        app_manager.run()
        logger.removeHandler(caplog.handler)

        assert "Invalid choice or option not available" in caplog.text
        assert "Exiting..." in caplog.text


def test_run_keyboard_interrupt(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Test run method handling KeyboardInterrupt."""
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", side_effect=KeyboardInterrupt()),
        patch.object(app_manager, "display_menu"),
        patch.object(app_manager, "cleanup") as mock_cleanup,
        caplog.at_level(logging.INFO),
    ):
        logger.addHandler(caplog.handler)
        app_manager.run()
        logger.removeHandler(caplog.handler)

        assert "KeyboardInterrupt received, exiting gracefully" in caplog.text
        mock_cleanup.assert_called_once()


def test_run_general_exception(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Test run method handling general exceptions."""
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", side_effect=Exception("Test error")),
        patch.object(app_manager, "display_menu"),
        patch.object(app_manager, "cleanup") as mock_cleanup,
        caplog.at_level(logging.INFO),
    ):
        logger.addHandler(caplog.handler)
        with pytest.raises(Exception, match="Test error"):
            app_manager.run()
        logger.removeHandler(caplog.handler)

        assert "Exception in main loop" in caplog.text
        mock_cleanup.assert_called_once()


def test_run_cleanup_called(app_manager: ApplicationManager) -> None:
    """Test cleanup is called when exiting normally."""
    with (
        patch("builtins.input", return_value="6"),
        patch.object(app_manager, "display_menu"),
        patch.object(app_manager, "cleanup") as mock_cleanup,
    ):
        app_manager.run()

        mock_cleanup.assert_called_once()
