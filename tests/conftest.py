"""Configuration for pytest."""

import importlib.util
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
except ImportError, AttributeError:
    # If matplotlib isn't installed or already configured, log the exception
    logger.exception("Could not configure matplotlib backend.")


MUTATED_MODULE_PATHS = (
    "src/application_manager.py",
    "src/checksum.py",
    "src/visualize_results.py",
)


def _load_mutated_modules(mutants_root: Path) -> None:
    for rel_path in MUTATED_MODULE_PATHS:
        module_name = Path(rel_path).stem
        module_path = mutants_root / rel_path
        if not module_path.exists():
            continue
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)


# Normal test imports are handled by pytest.ini (pythonpath = src).
# In mutmut's subprocess (cwd=mutants), preload only mutated targets.
if Path.cwd().name == "mutants" and "MUTANT_UNDER_TEST" in os.environ:
    root_src = Path.cwd().parent / "src"
    if root_src.exists():
        sys.path.insert(0, str(root_src))
    _load_mutated_modules(Path.cwd())
