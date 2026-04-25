<!-- markdownlint-disable MD033 MD041 -->
<div align="center">
<img src="https://github.com/carlosmazzei/signalbridge-controller/blob/main/assets/logo-pimatrix-dark.png#gh-dark-mode-only" alt="Signalbridge" width="150">
<img src="https://github.com/carlosmazzei/signalbridge-controller/blob/main/assets/logo-pimatrix-light.png#gh-light-mode-only" alt="Signalbridge" width="150">
</div>
<!-- markdownlint-enable MD033 MD041 -->

# SignalBridge - Test Suite

[![Tests](https://github.com/carlosmazzei/signalbridge-test-suite/actions/workflows/lint.yml/badge.svg)](https://github.com/carlosmazzei/signalbridge-test-suite/actions/workflows/lint.yml)
[![Coverage](https://codecov.io/gh/carlosmazzei/signalbridge-test-suite/branch/main/graph/badge.svg)](https://codecov.io/gh/carlosmazzei/signalbridge-test-suite)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A Python testing suite for the SignalBridge embedded controller (Raspberry Pi Pico). Communicates over UART using COBS framing and XOR checksums, providing latency measurement, baud rate sweep testing, stress testing, interactive command mode, system status monitoring, regression testing, keypad & ADC monitoring, and result visualization.

> [!TIP]
> This test suite is designed for the Raspberry Pi Pico-based SignalBridge controller firmware.

**Related repositories:**

- [SignalBridge breakout board](https://github.com/carlosmazzei/signalbridge-board) - Hardware design
- [SignalBridge test suite](https://github.com/carlosmazzei/signalbridge-test-suite) - This repository
- [SignalBridge firmware](https://github.com/carlosmazzei/signalbridge-controller) - Embedded C firmware
- [Firmware stress-test improvement plan](docs/firmware_stress_test_plan.md) - Roadmap to harden robustness validation

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
git clone https://github.com/carlosmazzei/signalbridge-test-suite.git
cd signalbridge-test-suite
uv sync
uv run src/main.py
```

### Headless execution (for .NET/service orchestration)

Use the non-interactive runner when invoking the suite from another process:

```bash
uv run src/runner_cli.py --mode latency --port /dev/ttyACM0 --baudrate 921600
uv run src/runner_cli.py --mode baud_sweep --baud-rates 115200,230400,921600
uv run src/runner_cli.py --mode stress --scenarios echo_burst,mixed_command_burst
uv run src/runner_cli.py --mode regression --output-json artifacts/regression.json
uv run src/runner_cli.py --mode stress --feedback-stdout --feedback-interval-ms 250
uv run src/runner_cli.py --mode latency --feedback-jsonl artifacts/progress.jsonl
```

The runner prints a JSON summary to stdout and can optionally write it to `--output-json`.
When a mode generates a report file, the summary includes `result_file` with the absolute path.
For real-time integration (e.g. .NET), enable `--feedback-stdout` to receive NDJSON progress
events (`run_started`, `heartbeat`, `mode_started`, `stress_progress`, `mode_finished`,
`run_finished`) or write them to a file using `--feedback-jsonl`.
Additionally, each runner invocation always writes a final envelope JSON file to `test_results/`
and exposes that path as `summary_file` in the final summary payload.

### Serial Port Configuration

Edit `src/const.py` to match your device:

```python
PORT_NAME = "/dev/cu.usbmodem101"  # macOS — adjust for your OS
BAUDRATE  = 921600                 # Must match firmware setting
TIMEOUT   = 0.1                   # Read timeout in seconds
```

Common port names:

| OS      | Example               |
| ------- | --------------------- |
| macOS   | `/dev/cu.usbmodem101` |
| Linux   | `/dev/ttyACM0`        |
| Windows | `COM3`                |

## ✨ Features

| Module               | Description                                                     |
| -------------------- | --------------------------------------------------------------- |
| Latency test         | High-precision roundtrip latency with P95 statistics            |
| Baud rate sweep      | Automated sweep across multiple baud rates                      |
| Stress test          | Five configurable scenarios (echo burst, mixed commands, etc.)  |
| Command mode         | Interactive hex command sending with real-time response display |
| Status mode          | Live statistics and FreeRTOS task performance monitoring        |
| Regression test      | Automated echo-command validation                               |
| Visualize results    | Boxplot, histogram, controller health, and error counter charts |
| Keypad & ADC monitor | Real-time sparkline display of ADC channels and keypad events   |

**Protocol stack:** COBS framing · XOR checksum · hardware RTS/CTS flow control · multi-threaded read/write

## 🎯 Usage Guide

### Main Menu

```
SignalBridge Test Suite  —  ● Connected  /dev/cu.usbmodem101  921,600 baud

  Connection
  [0]  Connect / Disconnect

  Tests
  [1]  Run latency test
  [2]  Regression test
  [3]  Baud rate sweep test
  [4]  Stress test (automated scenarios)

  Tools & Analysis
  [5]  Send command
  [6]  Status mode
  [7]  Visualize test results
  [8]  Keypad & ADC monitor

  [9]  Exit
```

Menu items that require a serial connection are dimmed when the device is not connected. Use `[0]` to toggle the connection at any time.

### 1. Latency Test

Measures roundtrip echo latency across configurable iterations and sample counts.

**Interactive prompts (7 steps):**

| #   | Parameter                     | Default |
| --- | ----------------------------- | ------- |
| 1   | Number of test iterations     | 5       |
| 2   | Message length (6–10 bytes)   | 10      |
| 3   | Min wait between samples (ms) | 0       |
| 4   | Max wait between samples (ms) | 100     |
| 5   | Samples per iteration         | 255     |
| 6   | Wait between iterations (s)   | 3       |
| 7   | Enable jitter                 | false   |

Results are saved to `test_results/{timestamp}_output.json` with latency samples, avg/min/max/P95, dropped message count, and bitrate.

### 2. Regression Test

Sends a fixed echo command and validates the exact response bytes, checksum, and timing. Exits with PASS/FAIL status.

### 3. Baud Rate Sweep Test

Sweeps through a list of baud rates and measures echo latency at each rate.

**Interactive prompts (4 steps):**

| #   | Parameter                   | Default |
| --- | --------------------------- | ------- |
| 1   | Use default baud rates?     | True    |
| 2   | Samples per baud rate       | 255     |
| 3   | Wait after each burst (s)   | 3       |
| 4   | Message length (6–10 bytes) | 10      |

Default baud rates: `[9600, 57600, 115200, 230400, 460800, 921600]`

### 4. Stress Test

Runs automated scenarios in sequence (or individually) with pass/fail verdicts. The default config registers five Phase-1 throughput/recovery scenarios plus eight deterministic fault-injection scenarios that exercise the firmware parser error counters.

| Scenario              | Profile           | Messages   | Key threshold                     |
| --------------------- | ----------------- | ---------- | --------------------------------- |
| `echo_burst`          | Echo only         | 500        | Drop ratio < 0.1 % · P95 < 50 ms  |
| `mixed_command_burst` | Echo + status     | 400        | Drop ratio < 0.5 % · P95 < 100 ms |
| `status_poll_storm`   | Status only       | 200        | Queue send errors = 0             |
| `baud_flip`           | Echo at each baud | 5 per rate | 0 % drop · recovery < 3 s         |
| `noise_and_recovery`  | Noise injection   | 10         | Full recovery · P95 < 2 000 ms    |

**Fault-injection scenarios** (defined in `src/stress_config.py`, generated by `src/fault_frames.py`): `fi_empty_frame`, `fi_too_short`, `fi_size_mismatch`, `fi_unknown_id`, `fi_bad_checksum`, `fi_payload_overflow`, `fi_single_overflow`, `fi_double_overflow_empty`. Each asserts that the corresponding firmware counter (`msg_malformed_error`, `checksum_error`, `unknown_cmd_error`, `buffer_overflow_error`, …) increments as expected while valid traffic remains serviceable.

A JSON report is written to `test_results/{run_id}_stress.json` after each run. A Rich summary table is printed to the terminal.

### 5. Send Command (Command Mode)

Interactive hex data entry with real-time incoming message display.

- Enter hex bytes without spaces or `0x` prefix (e.g. `003403010203`)
- Incoming frames are displayed with checksum validation
- Analog commands are filtered to reduce noise
- Type `x` or press `Ctrl+C` to exit

### 6. Status Mode

Polls and displays FreeRTOS statistics and task performance in Rich tables.

**Available actions:**

| Key | Action                           |
| --- | -------------------------------- |
| 1   | Request statistics status update |
| 2   | Request task status update       |
| 3   | Refresh display                  |
| 4   | Exit                             |

**Statistics monitored** (22 counters, full list in `src/base_test.py::STATISTICS_ITEMS`): queue send/receive errors, CDC queue send error, display/LED output errors, watchdog error, malformed-message and COBS-decode errors, receive/buffer overflow errors, checksum error, unknown-command error, bytes sent/received, resource-allocation error, output controller/init/driver/param errors, input queue init/full and input init errors.

**Tasks monitored:** `cdc_task`, `cdc_write_task`, `uart_event_task`, `led_status_task`, `decode_reception_task`, `process_outbound_task`, `adc_read_task`, `keypad_task` (includes rotary encoder), `idle_task` (system/heap info).

### 8. Keypad & ADC Monitor

Passively monitors incoming keypad and ADC frames in real-time without sending any commands to the device. The display auto-refreshes at 2 Hz using a live Rich panel.

**ADC panel** — one row per active channel:

| Column       | Detail                                                                     |
| ------------ | -------------------------------------------------------------------------- |
| Ch           | Channel number (0–15)                                                      |
| Last Value   | Most recent 12-bit ADC reading (0–4095), colour-coded green / yellow / red |
| Trend        | Unicode sparkline `▁▂▃▄▅▆▇█` of the last 10 values                         |
| Last Updated | UTC timestamp of the most recent sample                                    |

**Keypad events panel** — rolling log of the last 20 press/release events, newest first:

| Column    | Detail                                |
| --------- | ------------------------------------- |
| #         | Entry number (1 = most recent)        |
| Time      | UTC timestamp (HH:MM:SS.mmm)          |
| Col / Row | Matrix coordinates                    |
| State     | `PRESSED` (green) or `RELEASED` (dim) |

Press **ENTER** to exit back to the main menu.

> [!NOTE]
> The ADC task on the firmware runs continuously, so values update frequently. The keypad panel only appends an entry when a key state changes (press or release).

### 9. Visualize Test Results

Browse JSON files from `test_results/` (paginated, 10 per page) and choose a plot type:

| Key | Plot                                          |
| --- | --------------------------------------------- |
| 1   | Boxplot with dropped-message overlay          |
| 2   | Latency histogram with P95 marker             |
| 3   | Controller health trends                      |
| 4   | Error counter details (stacked bar + heatmap) |

Stress run JSON files (`*_stress.json`) are automatically routed to a dedicated three-panel visualization (drop ratio · P95 latency · error counters per scenario).

## 🔧 Protocol Reference

### Message Format (before COBS encoding)

| ID (11 bits) | CMD (5 bits) | Length | Payload | Checksum  |
| ------------ | ------------ | ------ | ------- | --------- |
| Bytes 0–1    | Byte 1       | Byte 2 | Byte 3+ | Last byte |

### COBS Framing

```
[COBS_DATA][0x00]   ← 0x00 is the frame delimiter
```

### Checksum

XOR over all payload bytes (excluding the checksum byte itself).

### Commands

| Command                     | Value | Description            |
| --------------------------- | ----- | ---------------------- |
| `ECHO_COMMAND`              | 20    | Echo test              |
| `KEY_COMMAND`               | 4     | Keypad event           |
| `ANALOG_COMMAND`            | 3     | ADC reading            |
| `STATISTICS_STATUS_COMMAND` | 23    | System statistics poll |
| `TASK_STATUS_COMMAND`       | 24    | FreeRTOS task poll     |

## 🛠️ Development

### Project Structure

```
signalbridge-test-suite/
├── src/
│   ├── main.py                # Entry point
│   ├── application_manager.py # Menu loop and module orchestration
│   ├── base_test.py           # Shared BaseTest infrastructure
│   ├── latency_test.py        # Latency measurement
│   ├── baud_rate_test.py      # Baud rate sweep
│   ├── stress_test.py         # Stress test orchestrator
│   ├── stress_config.py       # Scenario configuration schema
│   ├── stress_evaluator.py    # Verdict computation
│   ├── stress_reporter.py     # JSON report writer + Rich summary
│   ├── command_mode.py        # Interactive command interface
│   ├── status_mode.py         # FreeRTOS status monitoring
│   ├── keypad_adc_monitor.py  # Real-time keypad & ADC monitor
│   ├── regression_test.py     # Echo-command regression test
│   ├── fault_frames.py        # Deterministic malformed-frame generator
│   ├── visualize_results.py   # Matplotlib result visualizer
│   ├── serial_interface.py    # COBS/UART serial layer
│   ├── checksum.py            # XOR checksum utilities
│   ├── result_format.py       # JSON envelope + result filename helper
│   ├── ui_console.py          # Shared Rich Console instance
│   ├── logger_config.py       # Logging setup
│   └── const.py               # Serial port / folder constants
├── tests/                     # pytest test suite
├── docs/                      # Additional documentation
├── test_results/              # JSON output from test runs
├── pyproject.toml             # Dependencies and tool config
├── ruff.toml                  # Ruff linter/formatter config
├── pytest.ini                 # pytest configuration
├── logging_config.ini         # Logging configuration
└── ARCHITECTURE.md            # Authoritative architectural rules
```

### Common Commands

```bash
# Install dependencies
uv sync

# Run the application
uv run src/main.py

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_checksum.py

# Run a single test by name
uv run pytest tests/test_checksum.py::test_empty_data

# Lint
uv run ruff check src/

# Fix lint issues automatically
uv run ruff check --fix src/

# Format
uv run ruff format src/

# Mutation testing
uv run mutmut run
```

### Adding a New Test Mode

1. Subclass `BaseTest` (see `ARCHITECTURE.md` for mandatory patterns):

   ```python
   # src/my_test.py
   from base_test import BaseTest

   class MyTest(BaseTest):
       def execute_test(self) -> None: ...
       def handle_message(self, command: int, decoded_data: bytes) -> None: ...
   ```

2. Add a `ModuleConfig` entry in `ApplicationManager.__init__` (`application_manager.py`).

3. Assign the new key to the appropriate `_MENU_GROUPS` entry.

### Code Conventions

- **Python 3.13** target
- **ruff** with `select = ["ALL"]` — all lint rules enabled; specific ignores in `ruff.toml`
- Type hints on all functions and class attributes
- Thread safety: `_status_lock` (threading.Lock) guards shared dicts in `BaseTest`
- Tests use pytest-style `assert` with `unittest.mock` for hardware mocking
- Test results written to `test_results/` as JSON
- Pre-commit hooks run ruff lint + format and pytest on every commit. `mutmut` is a manual-stage hook (`pre-commit run mutmut --hook-stage manual`) and is not invoked by a plain `git commit`.

## 🚨 Troubleshooting

### Serial Port Access Denied

```bash
# Linux
sudo usermod -a -G dialout $USER   # then log out and back in

# macOS
ls -l /dev/cu.usbmodem*            # check ownership

# Windows
# Open Device Manager → Ports (COM & LPT) to find the correct COM port
```

### High Latency / Dropped Messages

- Reduce sample count or increase `max_wait`
- Close other applications sharing the USB hub
- Verify the firmware baudrate matches `BAUDRATE` in `const.py`
- Check cable quality and length

### Visualization Window Does Not Open

```bash
# Linux — install a Tk backend
sudo apt-get install python3-tk

# macOS / Windows — usually works without extra steps
```

### Log Files

```bash
tail -f app.log          # live log stream
grep ERROR app.log       # filter for errors
```

## 📄 License

This project is licensed under the GPL v3 License — see the [LICENSE](LICENSE) file for details.
