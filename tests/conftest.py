"""Configuration for pytest."""

import os
import sys
from pathlib import Path

# Ensure headless matplotlib backend for CI/mutation runs
os.environ.setdefault("MPLBACKEND", "Agg")
import logging

logger = logging.getLogger(__name__)

try:  # Best effort: force Agg before any pyplot import
    import matplotlib as mpl

    mpl.use("Agg", force=True)  # type: ignore[call-arg]
except (ImportError, AttributeError):
    # If matplotlib isn't installed or already configured, log the exception
    logger.exception("Could not configure matplotlib backend.")

# Add the src directory to Python's path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
