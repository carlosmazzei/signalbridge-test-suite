# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SignalBridge Test Suite is a Python application for testing a SignalBridge embedded controller (Raspberry Pi Pico). It communicates over UART using COBS framing and XOR checksums, providing latency measurement, baud rate sweep testing, stress testing with deterministic fault-frame injection, interactive command mode, system status monitoring, regression testing, keypad & ADC monitoring, and result visualization.

## Common Commands

The full command reference (build/publish, headless runner, troubleshooting) lives
in [README.md](README.md). The essentials:

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

# Mutation testing (mutates all files under src/ per setup.cfg)
uv run mutmut run
```

## Architecture

**CRITICAL REFERENCE: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for authoritative architectural rules.** A documentation index is available at [docs/README.md](docs/README.md).

All code modifications and new feature implementations must strictly adhere to the patterns, layers, and constraints described in `docs/ARCHITECTURE.md`. You must consult it before creating new test modes or adjusting the communication stack. This includes:
- Layer overview and orchestration via `ApplicationManager`
- Base classes like `BaseTest` and protocol implementations
- Buffer, Flow Control, and Thread Safety paradigms

## Code Conventions

The authoritative conventions are in [docs/ARCHITECTURE.md §9](docs/ARCHITECTURE.md#9-code-conventions)
(Python 3.13, ruff `select = ["ALL"]`, type hints, threading, logging). Beyond
those, when working in this repository:

- **Always check that the linter and `ruff check` are passing before proceeding.** Suppress only the minimal things.
- **Always check that the tests are passing** before concluding a task.
- `tests/conftest.py` forces the matplotlib `Agg` backend for headless CI.
- Pre-commit hooks run ruff lint+format and pytest on every commit. `mutmut` is a manual-stage hook (see `.pre-commit-config.yaml`) invoked on demand with `pre-commit run mutmut --hook-stage manual` or `uv run mutmut run`.
