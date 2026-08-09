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

"""Constants for the project."""

from importlib import metadata

TEST_RESULTS_FOLDER = "test_results"
PORT_NAME = "/dev/cu.usbmodem101"
BAUDRATE = 921600
TIMEOUT = 0.1

try:
    APP_VERSION = metadata.version("signalbridge-test-suite")
except metadata.PackageNotFoundError:
    APP_VERSION = "0.0.0-dev"
