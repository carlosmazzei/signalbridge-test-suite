"""Tests for ApplicationManager."""

from __future__ import annotations

import logging
import threading
import time as _time
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch

import pytest

from application_manager import ApplicationManager, Mode
from serial_interface import SerialInterface

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def mock_serial() -> Generator[SerialInterface, None, None]:
    """Fixture for mocked SerialInterface."""
    with patch("application_manager.SerialInterface") as mock:
        instance = Mock(spec=SerialInterface)
        mock.return_value = instance
        yield mock.return_value


@pytest.fixture
def app_manager(mock_serial: SerialInterface) -> ApplicationManager:
    """Fixture for ApplicationManager."""
    _ = mock_serial
    return ApplicationManager("COM1", 115200, 1.0)


def test_app_manager_constructs_serial_with_params() -> None:
    """Constructor should pass through serial params to SerialInterface."""
    with patch("application_manager.SerialInterface") as serial_cls:
        _ = ApplicationManager("PORTX", 57600, 0.25)
        serial_cls.assert_called_once_with("PORTX", 57600, 0.25)


def test_initialization(app_manager: ApplicationManager) -> None:
    """Test the initial state of ApplicationManager."""
    assert app_manager.mode == Mode.IDLE
    assert app_manager.modules == {}
    assert not app_manager.connected


def test_initialize_success(
    app_manager: ApplicationManager, mock_serial: SerialInterface
) -> None:
    """Test successful initialization when serial opens."""
    ms = cast("Mock", mock_serial)
    ms.open.return_value = True
    result = app_manager.initialize()
    assert result is True
    assert set(app_manager.modules) == {
        Mode.VISUALIZE,
        Mode.LATENCY,
        Mode.COMMAND,
        Mode.REGRESSION,
        Mode.STATUS,
    }
    ms.set_message_handler.assert_called_once()
    ms.start_reading.assert_called_once()
    app_manager.cleanup()


def test_initialize_failure(
    app_manager: ApplicationManager, mock_serial: SerialInterface
) -> None:
    """Test initialization when serial interface fails to open."""
    ms = cast("Mock", mock_serial)
    ms.open.return_value = False
    result = app_manager.initialize()
    assert result is False
    assert set(app_manager.modules) == {Mode.VISUALIZE}
    ms.set_message_handler.assert_not_called()
    ms.start_reading.assert_not_called()
    app_manager.cleanup()


def test_cleanup(app_manager: ApplicationManager, mock_serial: SerialInterface) -> None:
    """Test cleanup closes the serial interface."""
    app_manager.cleanup()
    ms = cast("Mock", mock_serial)
    ms.close.assert_called_once()


def test_disconnect_serial_clears_serial_modules(
    app_manager: ApplicationManager, mock_serial: SerialInterface
) -> None:
    """disconnect_serial closes port and removes only serial-required modules."""
    # Prime modules with a serial-required and a non-serial one
    app_manager.modules = {Mode.VISUALIZE: object(), Mode.LATENCY: object()}
    ms = cast("Mock", mock_serial)
    ms.is_open.return_value = True
    app_manager.disconnect_serial()
    ms.close.assert_called()
    assert Mode.LATENCY not in app_manager.modules
    assert Mode.VISUALIZE in app_manager.modules
    assert app_manager.mode == Mode.IDLE
    assert app_manager.connected is False


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (Mode.LATENCY, (1, b"d")),
        (Mode.COMMAND, (1, b"d", b"r")),
        (Mode.REGRESSION, (1, b"d", b"r")),
        (Mode.STATUS, (1, b"d")),
    ],
)
def test_handle_message_modes(
    app_manager: ApplicationManager, mode: Mode, expected: tuple
) -> None:
    """Ensure messages are dispatched to the active module."""
    mock_module = Mock()
    app_manager.modules[mode] = mock_module
    app_manager.mode = mode
    app_manager.handle_message(1, b"d", b"r")
    mock_module.handle_message.assert_called_once_with(*expected)


def test_display_menu_all_modules(
    app_manager: ApplicationManager, capsys: pytest.CaptureFixture[str]
) -> None:
    """Display menu when all modules are available."""
    for cfg in app_manager.module_configs:
        app_manager.modules[cfg.mode] = object()
    app_manager.connected = True
    app_manager.display_menu()
    out = capsys.readouterr().out
    assert "0. Disconnect from device" in out
    for cfg in app_manager.module_configs:
        assert f"{cfg.key}. {cfg.description}" in out
    assert f"{app_manager.exit_key}. Exit" in out


def test_app_manager_initial_mode_and_exit_key() -> None:
    """Ensure constructor sets mode and exit key deterministically."""
    with patch("application_manager.SerialInterface"):
        am = ApplicationManager("P", 9600, 0.1)
    assert am.mode == Mode.IDLE
    assert am.exit_key == "6"  # keys 1..5 defined above, exit is last+1


def test_display_menu_contains_expected_labels(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Menu text should contain the static labels for each option."""
    with patch("application_manager.SerialInterface"):
        am = ApplicationManager("P", 9600, 0.1)
    # Make all modules available
    for cfg in am.module_configs:
        am.modules[cfg.mode] = object()
    am.connected = True
    am.display_menu()
    out = capsys.readouterr().out
    assert "0. Disconnect from device" in out
    assert "1. Run latency test" in out
    assert "2. Send command" in out
    assert "3. Regression test" in out
    assert "4. Visualize test results" in out
    assert "5. Status mode" in out
    assert f"{am.exit_key}. Exit" in out


def test_display_menu_some_modules(
    app_manager: ApplicationManager, capsys: pytest.CaptureFixture[str]
) -> None:
    """Display menu when only visualization module is available."""
    app_manager.modules = {Mode.VISUALIZE: object()}
    app_manager.display_menu()
    out = capsys.readouterr().out
    assert "0. Connect to device" in out
    assert "4. Visualize test results" in out
    assert "1. Run latency test" not in out
    assert "5. Status mode" not in out


def test_handle_user_choice_runs_module(app_manager: ApplicationManager) -> None:
    """Selecting a menu option runs the associated module."""
    mock_module = Mock()
    app_manager.modules[Mode.LATENCY] = mock_module
    assert app_manager._handle_user_choice("1") is True
    mock_module.execute_test.assert_called_once()
    assert app_manager.mode == Mode.LATENCY


def test_handle_user_choice_unavailable(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Unavailability of module logs an informative message."""
    logger = logging.getLogger("application_manager")
    with caplog.at_level(logging.INFO):
        logger.addHandler(caplog.handler)
        app_manager._handle_user_choice("1")
        logger.removeHandler(caplog.handler)
    assert "Invalid choice or option not available" in caplog.text


def test_run_valid_choice(app_manager: ApplicationManager) -> None:
    """Run loop executes the selected module and exits."""
    mock_module = Mock()
    app_manager.modules[Mode.LATENCY] = mock_module
    with (
        patch("builtins.input", side_effect=["1", app_manager.exit_key]),
        patch.object(app_manager, "display_menu"),
    ):
        app_manager.run()
    mock_module.execute_test.assert_called_once()


def test_run_exit_choice(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Choosing exit immediately stops the loop."""
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", return_value=app_manager.exit_key),
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
    """Invalid menu selection is logged."""
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", side_effect=["x", app_manager.exit_key]),
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
    """Selecting an unavailable option is handled gracefully."""
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", side_effect=["1", app_manager.exit_key]),
        patch.object(app_manager, "display_menu"),
        caplog.at_level(logging.INFO),
    ):
        logger.addHandler(caplog.handler)
        app_manager.run()
        logger.removeHandler(caplog.handler)
    assert "Invalid choice or option not available" in caplog.text


def test_run_keyboard_interrupt(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Keyboard interrupt exits and triggers cleanup."""
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
    mock_cleanup.assert_called_once()
    assert "KeyboardInterrupt received, exiting gracefully" in caplog.text


def test_run_general_exception(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Unhandled exceptions bubble up and trigger cleanup."""
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", side_effect=Exception("boom")),
        patch.object(app_manager, "display_menu"),
        patch.object(app_manager, "cleanup") as mock_cleanup,
        caplog.at_level(logging.INFO),
    ):
        logger.addHandler(caplog.handler)
        with pytest.raises(Exception, match="boom"):
            app_manager.run()
        logger.removeHandler(caplog.handler)
    mock_cleanup.assert_called_once()
    assert "Exception in main loop" in caplog.text


def test_run_cleanup_called(app_manager: ApplicationManager) -> None:
    """Cleanup is invoked when exiting normally."""
    with (
        patch("builtins.input", return_value=app_manager.exit_key),
        patch.object(app_manager, "display_menu"),
        patch.object(app_manager, "cleanup") as mock_cleanup,
    ):
        app_manager.run()
    mock_cleanup.assert_called_once()


def test_toggle_connection_connects(app_manager: ApplicationManager) -> None:
    """When disconnected, toggling should attempt to connect."""
    app_manager.connected = False
    with (
        patch.object(app_manager, "connect_serial") as mock_connect,
        patch.object(app_manager, "disconnect_serial") as mock_disconnect,
    ):
        assert app_manager._toggle_connection() is True
    mock_connect.assert_called_once()
    mock_disconnect.assert_not_called()


def test_toggle_connection_disconnects(app_manager: ApplicationManager) -> None:
    """When connected, toggling should disconnect."""
    app_manager.connected = True
    with (
        patch.object(app_manager, "connect_serial") as mock_connect,
        patch.object(app_manager, "disconnect_serial") as mock_disconnect,
    ):
        assert app_manager._toggle_connection() is True
    mock_disconnect.assert_called_once()
    mock_connect.assert_not_called()


def test_monitor_connection_triggers_disconnect(
    app_manager: ApplicationManager,
    mock_serial: SerialInterface,
) -> None:
    """Monitor thread should disconnect if port closes."""
    app_manager.connected = True
    ms = cast("Mock", mock_serial)
    ms.is_open.return_value = False

    with patch.object(app_manager, "disconnect_serial") as mock_disconnect:
        app_manager.monitor_stop_event.clear()
        t = threading.Thread(target=app_manager._monitor_connection, daemon=True)
        t.start()
        _time.sleep(0.1)
        app_manager.monitor_stop_event.set()
        t.join(timeout=1)
    mock_disconnect.assert_called_once()
