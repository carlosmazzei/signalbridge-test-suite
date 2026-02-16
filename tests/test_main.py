"""Test the main module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from application_manager import ApplicationManager
from const import BAUDRATE, PORT_NAME, TIMEOUT
from main import main

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def mock_app_manager() -> Generator[Mock, Any]:
    """Mock app_manager."""
    with patch("main.application_manager.ApplicationManager") as mock_manager_cls:
        instance = Mock(spec=ApplicationManager)
        mock_manager_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_os() -> Generator[MagicMock | AsyncMock, Any]:
    """Patch os.system so 'clear' doesn't actually run."""
    with patch("os.system") as mock_system:
        yield mock_system


@pytest.fixture
def mock_logger() -> Generator[Mock, Any]:
    """Mock logger."""
    with patch("main.logger") as mock_logger:
        yield mock_logger


@pytest.fixture
def mock_serial_interface() -> Generator[Mock, Any]:
    """Patch 'SerialInterface' in application_manager.py, returning a mock."""
    with patch("application_manager.SerialInterface") as mock_serial_cls:
        serial_mock = Mock()
        mock_serial_cls.return_value = serial_mock
        # By default, pretend open() succeeds
        serial_mock.open.return_value = True
        yield serial_mock


def test_main_initializes_application_manager() -> None:
    """Test that main() initializes the ApplicationManager."""
    with patch("main.application_manager.ApplicationManager") as mock_manager_cls:
        instance = Mock(spec=ApplicationManager)
        mock_manager_cls.return_value = instance
        main()
        instance.initialize.assert_called_once()
        instance.run.assert_called_once()
        mock_manager_cls.assert_called_once_with(PORT_NAME, BAUDRATE, TIMEOUT)


def test_main_handles_initialization_failure(mock_app_manager: Mock) -> None:
    """Test that main() handles initialization failure."""
    mock_app_manager.initialize.return_value = False
    main()
    mock_app_manager.run.assert_called_once()


def test_main_calls_initialize_and_run(mock_app_manager: Mock) -> None:
    """Test that main() calls initialize() and run() on success."""
    main()
    mock_app_manager.initialize.assert_called_once()
    mock_app_manager.run.assert_called_once()
