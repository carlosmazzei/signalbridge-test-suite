# logger_config.py
import logging
import logging.config
import os
from pathlib import Path


def setup_logging(
    default_path: str = "logging_config.ini",
    default_level: int = logging.INFO,
    env_key: str = "LOG_CFG",
) -> None:
    """Open setup logging configuration from file."""
    path: Path = Path(__file__).parent.parent / default_path
    value = os.getenv(env_key, None)
    if value:
        path = Path(value)

    if Path(path).exists():
        logging.config.fileConfig(path.resolve(), disable_existing_loggers=False)
    else:
        logging.basicConfig(level=default_level)
