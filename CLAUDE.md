# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SignalBridge Test Suite is a Python application for testing a SignalBridge embedded controller (Raspberry Pi Pico). It communicates over UART using COBS framing and XOR checksums, providing latency measurement, baud rate sweep testing, interactive command mode, system status monitoring, regression testing, and result visualization.

## Common Commands

```bash
# Install dependencies
uv sync

# Run the application
uv run src/main.py

# Run all tests (coverage is always enabled via pytest.ini)
uv run pytest

# Run a single test file
uv run pytest tests/test_checksum.py

# Run a single test by name
uv run pytest tests/test_checksum.py::test_empty_data

# Lint and format
uv run ruff check src/
uv run ruff check --fix src/
uv run ruff format src/

# Mutation testing (targets: all possible files)
uv run mutmut run
```

## Architecture

**CRITICAL REFERENCE: See [ARCHITECTURE.md](ARCHITECTURE.md) for authoritative architectural rules.**

All code modifications and new feature implementations must strictly adhere to the patterns, layers, and constraints described in `ARCHITECTURE.md`. You must consult it before creating new test modes or adjusting the communication stack. This includes:
- Layer overview and orchestration via `ApplicationManager`
- Base classes like `BaseTest` and protocol implementations
- Buffer, Flow Control, and Thread Safety paradigms

## Code Conventions

- **Always check if linter and ruff check are passing before proceeding.** Make sure to suppress only the minimal things.
- **Always check if the tests are passing** before concluding a task.
- **Python 3.13** target (ruff config, CI)
- **ruff** with `select = ["ALL"]` — all lint rules enabled, specific ignores in `ruff.toml`
- Type hints on all functions and class attributes
- Tests use pytest-style `assert` with `unittest.mock` for hardware mocking
- `tests/conftest.py` forces matplotlib `Agg` backend for headless CI
- Thread safety: `_status_lock` (threading.Lock) guards shared statistics/task dicts in `BaseTest`
- Test results written to `test_results/` as JSON
- Pre-commit hooks run: ruff lint+format, pytest, mutmut
