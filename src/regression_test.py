# Copyright (C) 2026 SignalBridge contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Regression test module."""

import logging

from logger_config import setup_logging
from serial_interface import SerialCommand, SerialInterface

setup_logging()

logger = logging.getLogger(__name__)

# Payload sent by test_echo_command and expected back verbatim from the device.
ECHO_PAYLOAD = bytes([0x00, 0x34, 0x02, 0x01, 0x02])


class RegressionTest:
    """Regression test class."""

    def __init__(self, ser: SerialInterface) -> None:
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
                # decoded_data is the full frame: payload + trailing XOR
                # checksum. SerialInterface has already verified that byte, so
                # compare only the payload against what test_echo_command sent.
                echoed_payload = decoded_data[: len(ECHO_PAYLOAD)]
                if echoed_payload == ECHO_PAYLOAD:
                    logger.info("[OK] Echo command")
                else:
                    logger.info("[FAIL] Echo command")

                logger.info("Expected: %s", ECHO_PAYLOAD)
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
        self.ser.write(ECHO_PAYLOAD)

    def execute_test(self) -> None:
        """Execute regression test."""
        # Scenario 1: send echo command and expect to get the same message back
        self.test_echo_command()
