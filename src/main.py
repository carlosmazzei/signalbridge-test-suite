"""Main module for the application."""

import logging
import os

import application_manager
from const import BAUDRATE, PORT_NAME, TIMEOUT

logger = logging.getLogger(__name__)


def main() -> None:
    """Execute main loop."""
    app_manager = application_manager.ApplicationManager(PORT_NAME, BAUDRATE, TIMEOUT)

    os.system("clear")  # noqa: S605, S607  # Intentional terminal clearing
    app_manager.initialize()
    app_manager.run()


if __name__ == "__main__":
    main()
