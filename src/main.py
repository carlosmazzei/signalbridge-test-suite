from application_manager import ApplicationManager
from logger import Logger

MAX_LOG_MESSAGES = 20


def main() -> None:
    """Execute main loop."""
    logger = Logger(MAX_LOG_MESSAGES)
    port = "/dev/cu.usbmodem1234561"
    app_manager = ApplicationManager(port, 115200, 0.1, logger)

    app_manager.initialize()
    app_manager.run()


if __name__ == "__main__":
    main()
