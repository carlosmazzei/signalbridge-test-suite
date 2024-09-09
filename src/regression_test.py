import logging

from logger_config import setup_logging
from serial_interface import SerialCommand, SerialInterface

setup_logging()

logger = logging.getLogger(__name__)


class RegressionTest:
    """Regression test class."""

    def __init__(self, ser: SerialInterface):
        """Initialize Latency Test Class."""
        self.logger = logger
        self.ser = ser

    def handle_message(
        self,
        command: int,
        decoded_data: bytes,
        byte_string: bytes,
    ) -> None:
        """Handle message for regression test."""
        if command == SerialCommand.ECHO_COMMAND.value:
            try:
                if decoded_data == bytes([0x00, 0x34, 0x02, 0x01, 0x02]):
                    logger.info("[OK] Echo command")
                else:
                    logger.info("[FAIL] Echo command")

                logger.info(
                    "Expected: %s",
                    bytes([0x00, 0x34, 0x02, 0x01, 0x02]),
                )
                logger.info(
                    "Received: %s, command: %s, decoded: %s",
                    byte_string,
                    command,
                    decoded_data,
                )
                logger.info("Test ended")
            except IndexError:
                logger.exception("Invalid message (Index Error)")
                return

    def test_echo_command(self) -> None:
        """Test echo command."""
        payload = bytes([0x00, 0x34, 0x02, 0x01, 0x02])
        self.ser.write(payload)

    def execute_test(self) -> None:
        """Execute regression test."""
        # Scenario 1: send echo command and expect to get the same message back
        self.test_echo_command()
