# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SignalBridge Test Suite is a Python application for testing a SignalBridge embedded controller (Raspberry Pi Pico). It communicates over UART using COBS framing and XOR checksums, providing latency measurement, baud rate sweep testing, interactive command mode, system status monitoring, regression testing, and result visualization.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements.test.txt

# Run the application
python src/main.py

# Run all tests (coverage is always enabled via pytest.ini)
pytest

# Run a single test file
pytest tests/test_checksum.py

# Run a single test by name
pytest tests/test_checksum.py::test_empty_data

# Lint and format
ruff check src/
ruff check --fix src/
ruff format src/

# Mutation testing (targets: application_manager, checksum, visualize_results)
mutmut run
```

## Architecture

**Communication stack:**
- `SerialInterface` — Opens the serial port, runs reader/processor daemon threads, COBS-decodes incoming packets, dispatches to a registered `message_handler`. Uses RTS/CTS hardware flow control with high/low water marks.
- `BaseTest` — Abstract base class for all test modes. Handles message publishing (echo with counter), response handling (latency recording, statistics/task status parsing), P95 percentile calculations (numpy), and JSON output.

**Test modes** (all extend `BaseTest`):
- `LatencyTest` — Burst echo messages, measures roundtrip latency
- `BaudRateTest` — Sweeps baud rates running latency bursts at each
- `CommandMode` — Interactive hex command sender
- `StatusMode` — Real-time system statistics and FreeRTOS task metrics
- `RegressionTest` — Validates expected echo responses
- `VisualizeResults` — Matplotlib boxplot/histogram rendering from JSON results

**Orchestration:**
- `ApplicationManager` — Top-level controller. Uses `ModuleConfig` dataclasses to register modules declaratively. Manages serial connection lifecycle (background monitor thread), dynamic menu, and message dispatch routing. Modules declare `requires_serial=True/False` to control availability.
- `main.py` — Entry point, instantiates `ApplicationManager` with constants from `const.py`.

**Protocol details:**
- Wire format: COBS-encoded `[payload][xor_checksum]` terminated by `\x00`
- Command byte extraction: `data[1] & 0x1F` (5-bit command ID)
- Headers: `0x00 0x34` (echo), `0x00 0x37` (statistics), `0x00 0x38` (task status)

## Code Conventions

- **Python 3.14** target (ruff config, CI)
- **ruff** with `select = ["ALL"]` — all lint rules enabled, specific ignores in `ruff.toml`
- Type hints on all functions and class attributes
- Tests use pytest-style `assert` with `unittest.mock` for hardware mocking
- `tests/conftest.py` forces matplotlib `Agg` backend for headless CI
- Thread safety: `_status_lock` (threading.Lock) guards shared statistics/task dicts in `BaseTest`
- Test results written to `test_results/` as JSON
- Pre-commit hooks run: ruff lint+format, pytest, mutmut
