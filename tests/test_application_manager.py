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


@pytest.fixture(autouse=True)
def prevent_infinite_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Prevent infinite loops in application_manager.run during mutation testing.
    Mutmut might mutate the loop's exit condition, causing the test to hang until timeout.
    This fixture bounds the number of loop iterations.
    """
    original_handle_user_choice = ApplicationManager._handle_user_choice
    call_count = 0

    def mock_handle_user_choice(self: ApplicationManager, choice: str) -> bool:
        nonlocal call_count
        call_count += 1
        if call_count > 100:  # Arbitrary limit, plenty for any normal test
            msg = "Infinite loop detected during test"
            raise RuntimeError(msg)
        return original_handle_user_choice(self, choice)

    monkeypatch.setattr(
        ApplicationManager, "_handle_user_choice", mock_handle_user_choice
    )


@pytest.fixture
def mock_serial() -> Generator[SerialInterface]:
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
    assert app_manager.connected is False
    assert type(app_manager.connected) is bool  # strict type check for mutmut
    assert app_manager.monitor_thread is None
    assert app_manager.monitor_thread is None  # strict type check

    # Check that visualize config's handler is explicitly None
    vis_cfg = next(
        cfg for cfg in app_manager.module_configs if cfg.mode == Mode.VISUALIZE
    )
    assert vis_cfg.handler is None


def test_exit(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """_exit method logs message and returns False."""
    logger = logging.getLogger("application_manager")
    with caplog.at_level(logging.INFO):
        logger.addHandler(caplog.handler)
        result = app_manager._exit()
        logger.removeHandler(caplog.handler)

    assert result is False
    assert "Exiting..." in caplog.text


def test_initialize_success(
    app_manager: ApplicationManager, mock_serial: SerialInterface
) -> None:
    """Test successful initialization when serial opens."""
    ms = cast("Mock", mock_serial)
    ms.open.return_value = True
    with patch("application_manager.threading.Thread") as mock_thread_cls:
        result = app_manager.initialize()

    assert result is True
    assert set(app_manager.modules) == {
        Mode.VISUALIZE,
        Mode.LATENCY,
        Mode.COMMAND,
        Mode.REGRESSION,
        Mode.STATUS,
        Mode.BAUD_SWEEP,
        Mode.STRESS,
    }
    ms.set_message_handler.assert_called_once_with(app_manager.handle_message)
    ms.start_reading.assert_called_once_with()
    assert app_manager.connected is True

    # Check that monitor thread was started correctly
    mock_thread_cls.assert_called_once_with(
        target=app_manager._monitor_connection, daemon=True
    )
    mock_thread_cls.return_value.start.assert_called_once_with()

    app_manager.cleanup()


def test_initialize_failure(
    app_manager: ApplicationManager, mock_serial: SerialInterface
) -> None:
    """Test initialization when serial interface fails to open."""
    ms = cast("Mock", mock_serial)
    ms.open.return_value = False
    with patch("application_manager.threading.Thread") as mock_thread_cls:
        result = app_manager.initialize()

    assert result is False
    assert set(app_manager.modules) == {Mode.VISUALIZE}
    ms.set_message_handler.assert_not_called()
    ms.start_reading.assert_not_called()
    assert app_manager.connected is False

    # Still starts monitor thread
    mock_thread_cls.assert_called_once_with(
        target=app_manager._monitor_connection, daemon=True
    )
    mock_thread_cls.return_value.start.assert_called_once_with()

    app_manager.cleanup()


def test_cleanup(
    app_manager: ApplicationManager,
    mock_serial: SerialInterface,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test cleanup closes the serial interface."""
    logger = logging.getLogger("application_manager")
    with caplog.at_level(logging.INFO):
        logger.addHandler(caplog.handler)
        app_manager.cleanup()
        logger.removeHandler(caplog.handler)

    ms = cast("Mock", mock_serial)
    ms.close.assert_called_once_with()
    assert "Stopping read thread and closing serial port..." in caplog.text


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
        (Mode.STRESS, (1, b"d")),
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


def test_display_menu_all_modules(app_manager: ApplicationManager) -> None:
    """Display menu when all modules are available."""
    for cfg in app_manager.module_configs:
        app_manager.modules[cfg.mode] = object()
    app_manager.connected = True

    with patch("builtins.print") as mock_print:
        app_manager.display_menu()

    mock_print.assert_any_call("\nAvailable options:")
    mock_print.assert_any_call("0. Disconnect from device")
    for cfg in app_manager.module_configs:
        mock_print.assert_any_call(f"{cfg.key}. {cfg.description}")
    mock_print.assert_any_call(f"{app_manager.exit_key}. Exit")


def test_app_manager_initial_mode_and_exit_key() -> None:
    """Ensure constructor sets mode and exit key deterministically."""
    with patch("application_manager.SerialInterface"):
        am = ApplicationManager("P", 9600, 0.1)
    assert am.mode == Mode.IDLE
    assert am.connected is False
    assert type(am.connected) is bool
    assert am.monitor_thread is None
    assert am.monitor_thread is None
    assert am.exit_key == "8"  # keys 1..7 defined above, exit is last+1


def test_menu_items_structure(app_manager: ApplicationManager) -> None:
    """Verify menu items are correctly constructed from config."""
    items = app_manager.menu_items

    # Should have: Connect/Disconnect (0) + 7 modules + Exit
    assert len(items) == 9

    # 1. Connect/Disconnect
    assert items[0].key == "0"
    # Description is a lambda, check both states
    app_manager.connected = False
    assert items[0].description() == "Connect to device"
    app_manager.connected = True
    assert items[0].description() == "Disconnect from device"

    # 2. Modules (verify keys match config)
    # Map key to description
    item_map = {
        item.key: item.description() for item in items if item.key not in ("0", "8")
    }

    assert item_map["1"] == "Run latency test"
    assert item_map["2"] == "Send command"
    assert item_map["3"] == "Regression test"
    assert item_map["4"] == "Visualize test results"
    assert item_map["5"] == "Status mode"
    assert item_map["6"] == "Baud rate sweep test"
    assert item_map["7"] == "Stress test (automated scenarios)"

    # 3. Exit
    exit_item = items[-1]
    assert exit_item.key == "8"
    assert exit_item.description() == "Exit"


def test_display_menu_some_modules(app_manager: ApplicationManager) -> None:
    """Display menu when only visualization module is available."""
    app_manager.modules = {Mode.VISUALIZE: object()}
    with patch("builtins.print") as mock_print:
        app_manager.display_menu()

    mock_print.assert_any_call("\nAvailable options:")
    mock_print.assert_any_call("0. Connect to device")
    mock_print.assert_any_call("4. Visualize test results")
    # Verify we aren't printing more options than we should (0, 4, Exit = 3 options + header = 4 lines)
    assert mock_print.call_count == 4


def test_module_configs_builder_wiring(app_manager: ApplicationManager) -> None:
    """Module configs should construct expected module classes."""
    cfg_by_mode = {cfg.mode: cfg for cfg in app_manager.module_configs}

    assert set(cfg_by_mode) == {
        Mode.LATENCY,
        Mode.COMMAND,
        Mode.REGRESSION,
        Mode.VISUALIZE,
        Mode.STATUS,
        Mode.BAUD_SWEEP,
        Mode.STRESS,
    }

    with (
        patch("application_manager.BaudRateTest") as baud_cls,
        patch("application_manager.LatencyTest") as latency_cls,
        patch("application_manager.CommandMode") as command_cls,
        patch("application_manager.RegressionTest") as regression_cls,
        patch("application_manager.VisualizeResults") as visualize_cls,
        patch("application_manager.StatusMode") as status_cls,
    ):
        _ = cfg_by_mode[Mode.LATENCY].builder()
        latency_cls.assert_called_once_with(app_manager.serial_interface)

        _ = cfg_by_mode[Mode.COMMAND].builder()
        command_cls.assert_called_once_with(app_manager.serial_interface)

        _ = cfg_by_mode[Mode.REGRESSION].builder()
        regression_cls.assert_called_once_with(app_manager.serial_interface)

        visualize_cfg = cfg_by_mode[Mode.VISUALIZE]
        _ = visualize_cfg.builder()
        visualize_cls.assert_called_once_with()
        assert visualize_cfg.handler is None
        assert visualize_cfg.requires_serial is False

        _ = cfg_by_mode[Mode.STATUS].builder()
        status_cls.assert_called_once_with(app_manager.serial_interface)

        _ = cfg_by_mode[Mode.BAUD_SWEEP].builder()
        baud_cls.assert_called_once_with(app_manager.serial_interface)


def test_module_configs_complete_definition(app_manager: ApplicationManager) -> None:
    """Verify all module configurations have correct static properties."""
    configs = {cfg.mode: cfg for cfg in app_manager.module_configs}

    # 1. Latency
    cfg = configs[Mode.LATENCY]
    assert cfg.key == "1"
    assert cfg.description == "Run latency test"
    assert cfg.requires_serial is True

    # 2. Command
    cfg = configs[Mode.COMMAND]
    assert cfg.key == "2"
    assert cfg.description == "Send command"
    assert cfg.requires_serial is True

    # 3. Regression
    cfg = configs[Mode.REGRESSION]
    assert cfg.key == "3"
    assert cfg.description == "Regression test"
    assert cfg.requires_serial is True

    # 4. Visualize
    cfg = configs[Mode.VISUALIZE]
    assert cfg.key == "4"
    assert cfg.description == "Visualize test results"
    assert cfg.requires_serial is False

    # 5. Status
    cfg = configs[Mode.STATUS]
    assert cfg.key == "5"
    assert cfg.description == "Status mode"
    assert cfg.requires_serial is True

    # 6. Baud Sweep
    cfg = configs[Mode.BAUD_SWEEP]
    assert cfg.key == "6"
    assert cfg.description == "Baud rate sweep test"
    assert cfg.requires_serial is True

    # 7. Stress test
    cfg = configs[Mode.STRESS]
    assert cfg.key == "7"
    assert cfg.description == "Stress test (automated scenarios)"
    assert cfg.requires_serial is True

    # Verify no unexpected modes
    assert len(configs) == 7


def test_module_configs_runner_and_handler_wiring(
    app_manager: ApplicationManager,
) -> None:
    """Runner and handler callbacks should invoke expected module methods."""
    cfg_by_mode = {cfg.mode: cfg for cfg in app_manager.module_configs}

    latency_module = Mock()
    cfg_by_mode[Mode.LATENCY].runner(latency_module)
    latency_module.execute_test.assert_called_once()
    assert cfg_by_mode[Mode.LATENCY].handler is not None
    cfg_by_mode[Mode.LATENCY].handler(latency_module, 1, b"d", b"raw")
    latency_module.handle_message.assert_called_once_with(1, b"d")

    command_module = Mock()
    cfg_by_mode[Mode.COMMAND].runner(command_module)
    command_module.execute_command_mode.assert_called_once()
    assert cfg_by_mode[Mode.COMMAND].handler is not None
    cfg_by_mode[Mode.COMMAND].handler(command_module, 2, b"d", b"raw")
    command_module.handle_message.assert_called_once_with(2, b"d", b"raw")

    regression_module = Mock()
    cfg_by_mode[Mode.REGRESSION].runner(regression_module)
    regression_module.execute_test.assert_called_once()
    assert cfg_by_mode[Mode.REGRESSION].handler is not None
    cfg_by_mode[Mode.REGRESSION].handler(regression_module, 3, b"d", b"raw")
    regression_module.handle_message.assert_called_once_with(3, b"d", b"raw")

    visualize_module = Mock()
    cfg_by_mode[Mode.VISUALIZE].runner(visualize_module)
    visualize_module.execute_visualization.assert_called_once()
    assert cfg_by_mode[Mode.VISUALIZE].handler is None

    status_module = Mock()
    cfg_by_mode[Mode.STATUS].runner(status_module)
    status_module.execute_test.assert_called_once()
    assert cfg_by_mode[Mode.STATUS].handler is not None
    cfg_by_mode[Mode.STATUS].handler(status_module, 4, b"d", b"raw")
    status_module.handle_message.assert_called_once_with(4, b"d")

    baud_module = Mock()
    cfg_by_mode[Mode.BAUD_SWEEP].runner(baud_module)
    baud_module.execute_baud_test.assert_called_once()
    assert cfg_by_mode[Mode.BAUD_SWEEP].handler is not None
    cfg_by_mode[Mode.BAUD_SWEEP].handler(baud_module, 5, b"d", b"raw")
    baud_module.handle_message.assert_called_once_with(5, b"d")

    stress_module = Mock()
    cfg_by_mode[Mode.STRESS].runner(stress_module)
    stress_module.execute_test.assert_called_once()
    assert cfg_by_mode[Mode.STRESS].handler is not None
    cfg_by_mode[Mode.STRESS].handler(stress_module, 6, b"d", b"raw")
    stress_module.handle_message.assert_called_once_with(6, b"d")


def test_connect_disconnect_menu_item_uses_toggle_action(
    app_manager: ApplicationManager,
) -> None:
    """Menu item 0 should invoke the bound toggle action."""
    connect_item = next(item for item in app_manager.menu_items if item.key == "0")

    with (
        patch.object(app_manager, "connect_serial") as mock_connect,
        patch.object(app_manager, "disconnect_serial") as mock_disconnect,
    ):
        app_manager.connected = False
        assert connect_item.action() is True
        mock_connect.assert_called_once()
        mock_disconnect.assert_not_called()

        mock_connect.reset_mock()
        app_manager.connected = True
        assert connect_item.action() is True
        mock_disconnect.assert_called_once()
        mock_connect.assert_not_called()


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
    # Module LATENCY is not in modules
    logger = logging.getLogger("application_manager")
    with caplog.at_level(logging.INFO):
        logger.addHandler(caplog.handler)
        result = app_manager._handle_user_choice("1")
        result = app_manager._handle_user_choice("999")
    assert result is True
    assert any(
        record.message == "Invalid choice or option not available\n"
        for record in caplog.records
    )


def test_run_valid_choice(app_manager: ApplicationManager) -> None:
    """Run loop executes the selected module and exits."""
    mock_module = Mock()
    app_manager.modules[Mode.LATENCY] = mock_module
    with (
        patch("builtins.input", side_effect=["1", app_manager.exit_key]) as mock_input,
        patch.object(app_manager, "display_menu") as mock_display,
    ):
        app_manager.run()
    mock_module.execute_test.assert_called_once()
    assert mock_display.call_count == 2
    mock_input.assert_called_with("Enter a choice: ")


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
    # Output includes initial "Select an option:", invalid choice message,
    # and "Select an option:" again
    # We must strict check the caplog to kill 'XX' mutations
    assert any(
        record.message == "Invalid choice or option not available\n"
        for record in caplog.records
    )
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
    # The literal exact string checked in logging
    assert "Invalid choice or option not available\n" in caplog.text


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


def test_run_exception(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Run catches general exceptions and cleans up."""
    # Raise a generic Exception inside the loop
    with (
        patch.object(
            app_manager, "display_menu", side_effect=ValueError("Test exception")
        ),
        patch.object(app_manager, "cleanup") as mock_cleanup,
    ):
        logger = logging.getLogger("application_manager")
        with caplog.at_level(logging.ERROR):
            logger.addHandler(caplog.handler)
            with pytest.raises(ValueError, match="Test exception"):
                app_manager.run()
            logger.removeHandler(caplog.handler)

    mock_cleanup.assert_called_once()
    assert any(record.message == "Exception in main loop." for record in caplog.records)
    assert "Exception in main loop" in caplog.text


def test_run_cleanup_called(
    app_manager: ApplicationManager, caplog: pytest.LogCaptureFixture
) -> None:
    """Cleanup is invoked when exiting normally."""
    logger = logging.getLogger("application_manager")
    with (
        patch("builtins.input", return_value=app_manager.exit_key),
        patch.object(app_manager, "display_menu"),
        patch.object(app_manager, "cleanup") as mock_cleanup,
        caplog.at_level(logging.INFO),
    ):
        logger.addHandler(caplog.handler)
        app_manager.run()
        logger.removeHandler(caplog.handler)
    mock_cleanup.assert_called_once_with()
    # Implicit exit_key test
    assert "Exiting..." in caplog.text


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


def test_connect_serial_sets_connected_true(
    app_manager: ApplicationManager,
    mock_serial: SerialInterface,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """connect_serial sets connected=True when the port opens successfully."""
    ms = cast("Mock", mock_serial)
    ms.open.return_value = True

    logger = logging.getLogger("application_manager")
    with caplog.at_level(logging.INFO):
        logger.addHandler(caplog.handler)
        result = app_manager.connect_serial()
        logger.removeHandler(caplog.handler)

    assert result is True
    assert app_manager.connected is True

    # Assert module instances are actually built and stored
    for cfg in app_manager.module_configs:
        if cfg.requires_serial:
            assert app_manager.modules.get(cfg.mode) is not None

    ms.set_message_handler.assert_called_once_with(app_manager.handle_message)
    ms.start_reading.assert_called_once_with()
    ms.start_reading.assert_called_once_with()
    assert any(
        record.message == "Serial interface opened successfully."
        for record in caplog.records
    )
    app_manager.cleanup()


def test_connect_serial_sets_connected_false_on_failure(
    app_manager: ApplicationManager,
    mock_serial: SerialInterface,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """connect_serial sets connected=False when the port fails to open."""
    ms = cast("Mock", mock_serial)
    ms.open.return_value = False

    app_manager.modules = {}  # Start empty

    logger = logging.getLogger("application_manager")
    with caplog.at_level(logging.ERROR):
        logger.addHandler(caplog.handler)
        result = app_manager.connect_serial()
        logger.removeHandler(caplog.handler)

    assert result is False
    assert app_manager.connected is False

    # Modules shouldn't be added
    for cfg in app_manager.module_configs:
        if cfg.requires_serial:
            assert cfg.mode not in app_manager.modules

    ms.set_message_handler.assert_not_called()
    ms.start_reading.assert_not_called()
    ms.start_reading.assert_not_called()
    assert any(
        record.message
        == "Failed to open serial interface. Some features will be disabled."
        for record in caplog.records
    )


def test_is_module_available_true(app_manager: ApplicationManager) -> None:
    """_is_module_available returns True when the mode has a registered module."""
    app_manager.modules[Mode.LATENCY] = object()
    assert app_manager._is_module_available(Mode.LATENCY) is True


def test_is_module_available_false(app_manager: ApplicationManager) -> None:
    """_is_module_available returns False when the mode has no registered module."""
    assert app_manager._is_module_available(Mode.LATENCY) is False


def test_handle_message_no_handler(app_manager: ApplicationManager) -> None:
    """handle_message is a no-op when the active mode's config has no handler."""
    mock_module = Mock()
    app_manager.modules[Mode.VISUALIZE] = mock_module
    app_manager.mode = Mode.VISUALIZE  # VISUALIZE has handler=None
    app_manager.handle_message(1, b"d", b"r")
    mock_module.handle_message.assert_not_called()


def test_handle_message_no_module(app_manager: ApplicationManager) -> None:
    """handle_message is a no-op when no module is registered for the active mode."""
    app_manager.mode = Mode.LATENCY  # not present in modules
    app_manager.handle_message(1, b"d", b"r")  # must not raise


def test_monitor_connection_no_disconnect_when_still_open(
    app_manager: ApplicationManager,
    mock_serial: SerialInterface,
) -> None:
    """Monitor thread must NOT disconnect when the port is still open."""
    app_manager.connected = True
    ms = cast("Mock", mock_serial)
    ms.is_open.return_value = True  # port stays open

    with patch.object(app_manager, "disconnect_serial") as mock_disconnect:
        app_manager.monitor_stop_event.clear()
        t = threading.Thread(target=app_manager._monitor_connection, daemon=True)
        t.start()
        _time.sleep(0.1)
        app_manager.monitor_stop_event.set()
        t.join(timeout=1)
    mock_disconnect.assert_not_called()


def test_initialize_builds_non_serial_module_instance(
    app_manager: ApplicationManager, mock_serial: SerialInterface
) -> None:
    """initialize() stores a real module instance (not None) for VISUALIZE."""
    ms = cast("Mock", mock_serial)
    ms.open.return_value = False  # serial fails; only VISUALIZE is registered
    app_manager.initialize()
    assert app_manager.modules.get(Mode.VISUALIZE) is not None
    app_manager.cleanup()


def test_display_menu_shows_available_options_header(
    app_manager: ApplicationManager, capsys: pytest.CaptureFixture[str]
) -> None:
    """display_menu always prints the 'Available options:' header."""
    app_manager.display_menu()
    assert "Available options:" in capsys.readouterr().out


def test_handle_user_choice_condition_false_returns_true(
    app_manager: ApplicationManager,
) -> None:
    """When a menu item's condition is False, _handle_user_choice returns True."""
    # Mode.LATENCY not in modules → condition evaluates to False
    result = app_manager._handle_user_choice("1")
    assert result is True


def test_monitor_connection_triggers_disconnect(
    app_manager: ApplicationManager,
    mock_serial: SerialInterface,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Monitor thread should disconnect if port closes."""
    app_manager.connected = True
    ms = cast("Mock", mock_serial)
    ms.is_open.return_value = False

    logger = logging.getLogger("application_manager")
    with (
        patch.object(app_manager, "disconnect_serial") as mock_disconnect,
        caplog.at_level(logging.WARNING),
    ):
        logger.addHandler(caplog.handler)
        app_manager.monitor_stop_event.clear()
        t = threading.Thread(target=app_manager._monitor_connection, daemon=True)
        t.start()
        _time.sleep(0.1)
        app_manager.monitor_stop_event.set()
        t.join(timeout=1)
        logger.removeHandler(caplog.handler)

    mock_disconnect.assert_called_once()
    assert any(
        record.message == "Serial interface disconnected." for record in caplog.records
    )
