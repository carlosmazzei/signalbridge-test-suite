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


# Add the src directory to Python's path, robust across mutmut's mutants tree
def _find_src_dir(start: Path, max_up: int = 6) -> Path | None:
    p = start.resolve()
    for _ in range(max_up):
        candidate = p / "src"
        if candidate.exists():
            return candidate
        p = p.parent
    return None


src_dir = _find_src_dir(Path(__file__).parent)
if src_dir:
    sys.path.insert(0, str(src_dir))
