"""Main module for the application."""

import os

from application_manager import ApplicationManager


def main() -> None:
    """Execute main loop."""
    port = "/dev/cu.usbmodem1234561"
    app_manager = ApplicationManager(port, 115200, 0.1)

    os.system("clear")  # noqa: S605, S607
    app_manager.initialize()
    app_manager.run()


if __name__ == "__main__":
    main()
