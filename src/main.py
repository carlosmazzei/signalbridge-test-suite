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
