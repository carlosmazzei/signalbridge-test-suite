"""Module to setup logging configuration from file."""

from __future__ import annotations

import atexit
import logging
import logging.config
import logging.handlers
import os
import queue
import sys
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
    _rebind_stdout_handlers()


class _LateBoundStdout:
    """
    File-like proxy that resolves ``sys.stdout`` on every call.

    Lets ``alive_progress``'s stdout hook intercept log writes so records
    render above the pinned progress bar instead of corrupting its position.
    """

    def write(self, data: str) -> int:
        """Forward ``data`` to the current ``sys.stdout``."""
        return sys.stdout.write(data)

    def flush(self) -> None:
        """Flush the current ``sys.stdout``."""
        sys.stdout.flush()

    def __getattr__(self, name: str) -> object:
        """Forward any other attribute access to the current ``sys.stdout``."""
        return getattr(sys.stdout, name)


def _rebind_stdout_handlers() -> None:
    """Swap captured ``sys.stdout`` streams for a late-binding proxy."""
    proxy = _LateBoundStdout()
    targets: list[logging.Handler] = []
    if _Dispatch.listener is not None:
        targets.extend(_Dispatch.listener.handlers)
    for logger in _collect_configured_loggers():
        targets.extend(logger.handlers)

    seen: set[int] = set()
    for handler in targets:
        if id(handler) in seen:
            continue
        seen.add(id(handler))
        if (
            isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
            and getattr(handler, "stream", None) is sys.stdout
        ):
            handler.setStream(proxy)


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
