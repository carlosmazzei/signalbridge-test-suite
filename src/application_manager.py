"""Application Manager module."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from baud_rate_test import BaudRateTest
from command_mode import CommandMode
from latency_test import LatencyTest
from logger_config import setup_logging
from regression_test import RegressionTest
from serial_interface import SerialInterface
from status_mode import StatusMode
from stress_config import default_stress_config
from stress_test import StressTest
from visualize_results import VisualizeResults

if TYPE_CHECKING:
    from collections.abc import Callable

setup_logging()

logger = logging.getLogger(__name__)


class Mode(Enum):
    """Application mode Enum."""

    IDLE = 0
    LATENCY = 1
    COMMAND = 2
    REGRESSION = 3
    VISUALIZE = 4
    STATUS = 5
    BAUD_SWEEP = 6
    STRESS = 7


@dataclass
class MenuItem:
    """Representation of a menu item."""

    key: str
    description: Callable[[], str]
    action: Callable[[], bool]
    condition: Callable[[], bool] = lambda: True


@dataclass
class ModuleConfig:
    """Configuration for a module handled by ApplicationManager."""

    key: str
    mode: Mode
    description: str
    builder: Callable[[], Any]
    runner: Callable[[Any], None]
    handler: Callable[[Any, int, bytes, bytes], None] | None = None
    requires_serial: bool = True


class ApplicationManager:
    """Manage the overall application flow and module coordination."""

    def __init__(self, port: str, baudrate: int, timeout: float) -> None:
        """Instantiate with serial connection parameters."""
        self.serial_interface: SerialInterface = SerialInterface(
            port, baudrate, timeout
        )
        self.mode: Mode = Mode.IDLE
        self.connected: bool = False
        self.monitor_thread: threading.Thread | None = None
        self.monitor_stop_event = threading.Event()
        self.modules: dict[Mode, Any] = {}

        self.module_configs: list[ModuleConfig] = [
            ModuleConfig(
                key="1",
                mode=Mode.LATENCY,
                description="Run latency test",
                builder=lambda: LatencyTest(self.serial_interface),
                runner=lambda module: module.execute_test(),
                handler=lambda module, command, data, _unused: module.handle_message(
                    command, data
                ),
            ),
            ModuleConfig(
                key="2",
                mode=Mode.COMMAND,
                description="Send command",
                builder=lambda: CommandMode(self.serial_interface),
                runner=lambda module: module.execute_command_mode(),
                handler=lambda module, command, data, byte_string: (
                    module.handle_message(command, data, byte_string)
                ),
            ),
            ModuleConfig(
                key="3",
                mode=Mode.REGRESSION,
                description="Regression test",
                builder=lambda: RegressionTest(self.serial_interface),
                runner=lambda module: module.execute_test(),
                handler=lambda module, command, data, byte_string: (
                    module.handle_message(command, data, byte_string)
                ),
            ),
            ModuleConfig(
                key="4",
                mode=Mode.VISUALIZE,
                description="Visualize test results",
                builder=lambda: VisualizeResults(),  # noqa: PLW0108  # lambda needed to support mock patching during tests
                runner=lambda module: module.execute_visualization(),
                requires_serial=False,
            ),
            ModuleConfig(
                key="5",
                mode=Mode.STATUS,
                description="Status mode",
                builder=lambda: StatusMode(self.serial_interface),
                runner=lambda module: module.execute_test(),
                handler=lambda module, command, data, _unused: module.handle_message(
                    command, data
                ),
            ),
            ModuleConfig(
                key="6",
                mode=Mode.BAUD_SWEEP,
                description="Baud rate sweep test",
                builder=lambda: BaudRateTest(self.serial_interface),
                runner=lambda module: module.execute_baud_test(),
                handler=lambda module, command, data, _unused: module.handle_message(
                    command, data
                ),
            ),
            ModuleConfig(
                key="7",
                mode=Mode.STRESS,
                description="Stress test (automated scenarios)",
                builder=lambda: StressTest(
                    self.serial_interface, default_stress_config()
                ),
                runner=lambda module: module.execute_test(),
                handler=lambda module, command, data, _unused: module.handle_message(
                    command, data
                ),
            ),
        ]
        self.module_configs_by_mode = {cfg.mode: cfg for cfg in self.module_configs}

        self.menu_items: list[MenuItem] = [
            MenuItem(
                "0",
                lambda: (
                    "Disconnect from device" if self.connected else "Connect to device"
                ),
                self._toggle_connection,
            )
        ]
        for cfg in self.module_configs:
            self.menu_items.append(
                MenuItem(
                    cfg.key,
                    lambda desc=cfg.description: desc,
                    self._create_module_action(cfg.mode),
                    lambda cfg=cfg: self._is_module_available(cfg.mode),
                )
            )
        exit_key_int = max(int(cfg.key) for cfg in self.module_configs) + 1
        self.exit_key = str(exit_key_int)
        self.menu_items.append(MenuItem(self.exit_key, lambda: "Exit", self._exit))

    def _is_module_available(self, mode: Mode) -> bool:
        """Check if a module for the given mode is available."""
        return mode in self.modules

    def initialize(self) -> bool:
        """Initialize serial interface and set up components."""
        for cfg in self.module_configs:
            if not cfg.requires_serial:
                self.modules[cfg.mode] = cfg.builder()
        result = self.connect_serial()
        self.monitor_stop_event.clear()
        self.monitor_thread = threading.Thread(
            target=self._monitor_connection, daemon=True
        )
        self.monitor_thread.start()
        return result

    def connect_serial(self) -> bool:
        """Open the serial interface and initialize serial-dependent modules."""
        if self.serial_interface.open():
            self.serial_interface.set_message_handler(self.handle_message)
            self.serial_interface.start_reading()
            for cfg in self.module_configs:
                if cfg.requires_serial:
                    self.modules[cfg.mode] = cfg.builder()
            self.connected = True
            logger.info("Serial interface opened successfully.")
            return True
        logger.error("Failed to open serial interface. Some features will be disabled.")
        self.connected = False
        return False

    def disconnect_serial(self) -> None:
        """Disconnect the serial interface and disable related modules."""
        if self.serial_interface.is_open():
            self.serial_interface.close()
        for cfg in self.module_configs:
            if cfg.requires_serial:
                self.modules.pop(cfg.mode, None)
        self.mode = Mode.IDLE
        self.connected = False

    def _monitor_connection(self) -> None:
        """Background thread that monitors the serial connection."""
        while not self.monitor_stop_event.is_set():
            if self.connected and not self.serial_interface.is_open():
                logger.warning("Serial interface disconnected.")
                self.disconnect_serial()
            time.sleep(0.5)

    def _toggle_connection(self) -> bool:
        """Toggle the connection state."""
        if self.connected:
            self.disconnect_serial()
        else:
            self.connect_serial()
        return True

    def _create_module_action(self, mode: Mode) -> Callable[[], bool]:
        """Create a menu action for the given mode."""

        def action() -> bool:
            module = self.modules.get(mode)
            if module:
                self.mode = mode
                cfg = self.module_configs_by_mode[mode]
                cfg.runner(module)
            else:
                logger.info(
                    "%s mode is not available. Serial interface is not connected.",
                    mode.name.title(),
                )
            return True

        return action

    def _exit(self) -> bool:
        """Handle exiting the application."""
        logger.info("Exiting...")
        return False

    def handle_message(
        self, command: int, decoded_data: bytes, byte_string: bytes
    ) -> None:
        """Dispatch incoming messages to the active module."""
        module = self.modules.get(self.mode)
        if not module:
            return
        cfg = self.module_configs_by_mode.get(self.mode)
        if cfg and cfg.handler:
            cfg.handler(module, command, decoded_data, byte_string)

    def cleanup(self) -> None:
        """Cleanup resources and close serial interface."""
        logger.info("Stopping read thread and closing serial port...")
        self.monitor_stop_event.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join()
        self.disconnect_serial()

    def display_menu(self) -> None:
        """Display the menu of available options."""
        print("\nAvailable options:")
        for item in self.menu_items:
            if item.condition():
                print(f"{item.key}. {item.description()}")

    def _handle_user_choice(self, choice: str) -> bool:
        """Handle user choice and return whether to continue the loop."""
        for item in self.menu_items:
            if choice == item.key:
                if item.condition():
                    return item.action()
                logger.info("Invalid choice or option not available\n")
                return True
        logger.info("Invalid choice or option not available\n")
        return True

    def run(self) -> None:
        """Run the main application loop."""
        try:
            while True:
                self.display_menu()
                choice = input("Enter a choice: ")
                if not self._handle_user_choice(choice):
                    break
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received, exiting gracefully.")
        except Exception:
            logger.exception("Exception in main loop.")
            raise
        finally:
            self.cleanup()
