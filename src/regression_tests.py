from cobs import cobs
from logger import Logger
from serial import Serial


def handle_message(
    logger: Logger, command: int, decoded_data: bytes, byte_string: bytes
) -> None:
    """Handle message for regression test."""
    if command == 20:
        try:
            if decoded_data == bytes([0x00, 0x34, 0x02, 0x01, 0x02]):
                logger.display_log("[OK] Echo command")
            else:
                logger.display_log("[FAIL] Echo command")

            logger.display_log(f"Expected: {bytes([0x00, 0x34, 0x02, 0x01, 0x02])}")
            logger.display_log(
                f"Received: {byte_string}, command: {command}, decoded: {decoded_data}"
            )
            logger.display_log("Test ended")
        except IndexError:
            logger.display_log("Invalid message (Index Error)")
            return


def test_echo_command(ser: Serial) -> None:
    """Test echo command."""
    payload = bytes([0x00, 0x34, 0x02, 0x01, 0x02])
    message = cobs.encode(payload)
    message += b"\x00"
    ser.write(message)


def execute_test(ser: Serial) -> None:
    """Execute regression test."""
    # Scenario 1: send echo command and expect to get the same message back
    test_echo_command(ser)
