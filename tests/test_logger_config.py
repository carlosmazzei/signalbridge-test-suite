"""Tests for logger_config module."""

from __future__ import annotations

import logging
import logging.handlers
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from logger_config import _Dispatch, _install_queue_dispatch, setup_logging


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


class TestQueueDispatch:
    """Exercise the non-blocking queue-based logging dispatcher."""

    @pytest.fixture(autouse=True)
    def _isolate_logging(self) -> None:
        saved_listener = _Dispatch.listener
        if saved_listener is not None:
            saved_listener.stop()
        _Dispatch.listener = None

        root = logging.getLogger()
        saved_root_handlers = list(root.handlers)
        saved_root_level = root.level
        saved_children: dict[str, tuple[list[logging.Handler], int]] = {}
        for name in list(logging.root.manager.loggerDict):
            existing = logging.getLogger(name)
            if isinstance(existing, logging.Logger):
                saved_children[name] = (list(existing.handlers), existing.level)
                existing.handlers = []

        root.handlers = []
        root.setLevel(logging.WARNING)
        yield

        if _Dispatch.listener is not None:
            _Dispatch.listener.stop()
            _Dispatch.listener = None
        root.handlers = saved_root_handlers
        root.setLevel(saved_root_level)
        for name, (handlers, level) in saved_children.items():
            restored = logging.getLogger(name)
            restored.handlers = handlers
            restored.setLevel(level)

    def test_install_replaces_real_handlers_with_queue_handler(self) -> None:
        sink = logging.Handler()
        root = logging.getLogger()
        root.addHandler(sink)

        _install_queue_dispatch()

        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.handlers.QueueHandler)
        assert _Dispatch.listener is not None

    def test_listener_owns_original_handlers(self) -> None:
        sink = logging.Handler()
        logging.getLogger().addHandler(sink)

        _install_queue_dispatch()

        assert _Dispatch.listener is not None
        assert sink in _Dispatch.listener.handlers

    def test_records_are_delivered_through_queue(self) -> None:
        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        sink = _Capture(level=logging.DEBUG)
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        root.addHandler(sink)

        _install_queue_dispatch()
        logging.getLogger("queue_dispatch_test").info("hello")

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not captured:
            time.sleep(0.01)

        assert any(rec.getMessage() == "hello" for rec in captured)

    def test_install_is_idempotent(self) -> None:
        sink = logging.Handler()
        logging.getLogger().addHandler(sink)

        _install_queue_dispatch()
        first_listener = _Dispatch.listener
        _install_queue_dispatch()
        second_listener = _Dispatch.listener

        assert first_listener is not None
        assert second_listener is not None
        # The second call is a no-op: no real handlers left to collect.
        assert first_listener is second_listener
