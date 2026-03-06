"""Main module for the application."""

import logging

import application_manager
from const import BAUDRATE, PORT_NAME, TIMEOUT
from ui_console import console

logger = logging.getLogger(__name__)


def main() -> None:
    """Execute main loop."""
    app_manager = application_manager.ApplicationManager(PORT_NAME, BAUDRATE, TIMEOUT)

    console.clear()
    app_manager.initialize()
    app_manager.run()


if __name__ == "__main__":
    main()
