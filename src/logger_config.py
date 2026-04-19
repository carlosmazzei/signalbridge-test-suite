"""Module to setup logging configuration from file."""

from __future__ import annotations

import atexit
import logging
import logging.config
import logging.handlers
import os
import queue
from pathlib import Path


class _Dispatch:
    """Module-local state for the async logging dispatcher."""

    listener: logging.handlers.QueueListener | None = None
    atexit_registered: bool = False


def setup_logging(
    default_path: str = "logging_config.ini",
    default_level: int = logging.INFO,
    env_key: str = "LOG_CFG",
) -> None:
    """
    Configure logging with a non-blocking, queue-based dispatcher.

    Loggers receive a single `QueueHandler` that enqueues records and returns
    immediately; a background `QueueListener` thread owns the real I/O
    handlers so stdout/file writes never block producer threads.
    """
    path: Path = Path(__file__).parent.parent / default_path
    value = os.getenv(env_key, None)
    if value:
        path = Path(value)

    if Path(path).exists():
        logging.config.fileConfig(path.resolve(), disable_existing_loggers=False)
    else:
        logging.basicConfig(level=default_level)

    _install_queue_dispatch()


def _collect_configured_loggers() -> list[logging.Logger]:
    """Return the root logger plus every named logger currently registered."""
    loggers: list[logging.Logger] = [logging.getLogger()]
    for name in list(logging.root.manager.loggerDict):
        candidate = logging.getLogger(name)
        if isinstance(candidate, logging.Logger):
            loggers.append(candidate)
    return loggers


def _collect_real_handlers(loggers: list[logging.Logger]) -> list[logging.Handler]:
    """Return unique, non-queue handlers attached to the given loggers."""
    seen: set[int] = set()
    real_handlers: list[logging.Handler] = []
    for logger in loggers:
        for handler in logger.handlers:
            if isinstance(handler, logging.handlers.QueueHandler):
                continue
            if id(handler) not in seen:
                seen.add(id(handler))
                real_handlers.append(handler)
    return real_handlers


def _install_queue_dispatch() -> None:
    """Route every configured logger through a queue served by one thread."""
    loggers = _collect_configured_loggers()
    real_handlers = _collect_real_handlers(loggers)

    if not real_handlers:
        return

    log_queue: queue.Queue[logging.LogRecord] = queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(log_queue)

    for logger in loggers:
        if logger.handlers:
            logger.handlers = [queue_handler]

    if _Dispatch.listener is not None:
        _Dispatch.listener.stop()

    _Dispatch.listener = logging.handlers.QueueListener(
        log_queue,
        *real_handlers,
        respect_handler_level=True,
    )
    _Dispatch.listener.start()

    if not _Dispatch.atexit_registered:
        atexit.register(_stop_listener)
        _Dispatch.atexit_registered = True


def _stop_listener() -> None:
    """Drain the queue and stop the background dispatcher thread."""
    if _Dispatch.listener is not None:
        _Dispatch.listener.stop()
        _Dispatch.listener = None
