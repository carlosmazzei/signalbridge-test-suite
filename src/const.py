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
