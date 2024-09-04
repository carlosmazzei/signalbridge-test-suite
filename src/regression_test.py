from logger import Logger
from serial_interface import SerialCommand, SerialInterface


class RegressionTest:
    """Regression test class."""

    def __init__(self, ser: SerialInterface, logger: Logger):
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
        if command == SerialCommand.ECHO_COMMAND:
            try:
                if decoded_data == bytes([0x00, 0x34, 0x02, 0x01, 0x02]):
                    self.logger.display_log("[OK] Echo command")
                else:
                    self.logger.display_log("[FAIL] Echo command")

                self.logger.display_log(
                    f"Expected: {bytes([0x00, 0x34, 0x02, 0x01, 0x02])}",
                )
                self.logger.display_log(
                    f"Received: {byte_string}, command: {command}, decoded: {decoded_data}",
                )
                self.logger.display_log("Test ended")
            except IndexError:
                self.logger.display_log("Invalid message (Index Error)")
                return

    def test_echo_command(self) -> None:
        """Test echo command."""
        payload = bytes([0x00, 0x34, 0x02, 0x01, 0x02])
        self.ser.write(payload)

    def execute_test(self) -> None:
        """Execute regression test."""
        # Scenario 1: send echo command and expect to get the same message back
        self.test_echo_command()
