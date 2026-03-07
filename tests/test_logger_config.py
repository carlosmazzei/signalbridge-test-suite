"""Tests for logger_config module."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import patch

from logger_config import setup_logging


class TestSetupLogging:
    def test_loads_config_when_file_exists(self) -> None:
        with (
            patch.object(Path, "exists", return_value=True),
            patch("logging.config.fileConfig") as mock_file_config,
            patch("logging.basicConfig") as mock_basic,
        ):
            setup_logging()

        mock_file_config.assert_called_once()
        assert mock_file_config.call_args[1]["disable_existing_loggers"] is False
        mock_basic.assert_not_called()

    def test_falls_back_to_basic_config_when_file_missing(self) -> None:
        with (
            patch.object(Path, "exists", return_value=False),
            patch("logging.config.fileConfig") as mock_file_config,
            patch("logging.basicConfig") as mock_basic,
        ):
            setup_logging()

        mock_file_config.assert_not_called()
        mock_basic.assert_called_once_with(level=logging.INFO)

    def test_env_var_overrides_default_path(self) -> None:
        original = os.environ.get("LOG_CFG")
        os.environ["LOG_CFG"] = "/custom/path/logging.ini"
        try:
            with (
                patch.object(Path, "exists", return_value=False),
                patch("logging.basicConfig") as mock_basic,
            ):
                setup_logging()
            mock_basic.assert_called_once_with(level=logging.INFO)
        finally:
            if original is None:
                os.environ.pop("LOG_CFG", None)
            else:
                os.environ["LOG_CFG"] = original

    def test_env_var_path_used_when_set(self) -> None:
        original = os.environ.get("LOG_CFG")
        os.environ["LOG_CFG"] = "/custom/path/logging.ini"
        try:
            with (
                patch.object(Path, "exists", return_value=True),
                patch("logging.config.fileConfig") as mock_file_config,
            ):
                setup_logging()
            # The resolved path should come from the env var
            called_path = mock_file_config.call_args[0][0]
            assert "custom" in str(called_path)
        finally:
            if original is None:
                os.environ.pop("LOG_CFG", None)
            else:
                os.environ["LOG_CFG"] = original

    def test_default_level_is_info(self) -> None:
        with (
            patch.object(Path, "exists", return_value=False),
            patch("logging.basicConfig") as mock_basic,
        ):
            setup_logging()
        mock_basic.assert_called_once_with(level=logging.INFO)

    def test_custom_default_level(self) -> None:
        with (
            patch.object(Path, "exists", return_value=False),
            patch("logging.basicConfig") as mock_basic,
        ):
            setup_logging(default_level=logging.DEBUG)
        mock_basic.assert_called_once_with(level=logging.DEBUG)

    def test_disable_existing_loggers_is_false(self) -> None:
        with (
            patch.object(Path, "exists", return_value=True),
            patch("logging.config.fileConfig") as mock_file_config,
        ):
            setup_logging()
        _, kwargs = mock_file_config.call_args
        assert kwargs["disable_existing_loggers"] is False
