# SignalBridge Test Suite — Architecture Reference

> **Purpose:** This document is the authoritative guide for Claude Code when implementing new features or modifying existing code. All changes must conform to the patterns described here.

---

## 1. Layer Overview

```
┌─────────────────────────────────────────────────────┐
│                     main.py                         │  Entry point
├─────────────────────────────────────────────────────┤
│               ApplicationManager                    │  Orchestration
│   (Mode enum, ModuleConfig, menu, message routing)  │
├──────────┬──────────────────────────┬───────────────┤
│ BaseTest │   Module layer           │ VisualizeRes. │  Test modes
│ (abstract│  LatencyTest             │ (no serial)   │
│  base)   │  BaudRateTest            │               │
│          │  StatusMode              │               │
│          │  RegressionTest          │               │
│          │  CommandMode             │               │
├──────────┴──────────────────────────┴───────────────┤
│               SerialInterface                        │  Transport
│  (COBS encode/decode, threads, flow control)        │
├─────────────────────────────────────────────────────┤
│          checksum.py  ·  const.py                   │  Utilities
└─────────────────────────────────────────────────────┘
```

---

## 2. Module Registration — The Only Way to Add a Test Mode

New test modes are registered **exclusively** through the `module_configs` list in `ApplicationManager.__init__`. Do not add ad-hoc attributes or call module code directly from `run()`.

### `ModuleConfig` dataclass fields

| Field | Type | Description |
|---|---|---|
| `key` | `str` | Menu key the user presses (sequential integer string) |
| `mode` | `Mode` | Unique `Mode` enum value |
| `description` | `str` | Text shown in the menu |
| `builder` | `Callable[[], Any]` | Factory called after serial connects; returns the module instance |
| `runner` | `Callable[[Any], None]` | Called when the user selects the mode; receives the module instance |
| `handler` | `Callable[[Any, int, bytes, bytes], None] \| None` | Called for every incoming message while this mode is active; `None` if the module never reads from the device |
| `requires_serial` | `bool` | `True` → built after serial connects, torn down on disconnect; `False` → built at startup, always available (e.g. `VisualizeResults`) |

### Example — adding a new mode

```python
# 1. Add a new value to the Mode enum
class Mode(Enum):
    ...
    MY_NEW_MODE = 7          # next integer after the current max

# 2. Append a ModuleConfig entry (in __init__, after the existing entries)
ModuleConfig(
    key="7",
    mode=Mode.MY_NEW_MODE,
    description="My new test",
    builder=lambda: MyNewMode(self.serial_interface),
    runner=lambda module: module.execute_test(),
    handler=lambda module, command, data, _unused: module.handle_message(command, data),
    requires_serial=True,
),
```

`ApplicationManager` automatically:
- Inserts the menu item
- Routes messages to the handler while the mode is active
- Builds/tears down the module on serial connect/disconnect

---

## 3. Message Routing

```
SerialInterface._process_complete_message()
  │  COBS decode → extract command byte (data[1] & 0x1F)
  └─► ApplicationManager.handle_message(command, decoded_data, byte_string)
        │  look up self.modules[self.mode]
        └─► ModuleConfig.handler(module, command, decoded_data, byte_string)
              └─► module.handle_message(command, decoded_data)
```

**Rules:**
- Only the **active mode's** handler receives messages; no broadcasting.
- `ApplicationManager.handle_message` is the single entry point registered with `SerialInterface.set_message_handler()`.
- `handler` lambdas in `ModuleConfig` must match the signature `(module, command: int, decoded_data: bytes, byte_string: bytes) -> None`. Use `_unused` for parameters the module does not need.

---

## 4. Base Class — Mandatory for Serial Test Modes

Every test mode that communicates with the device **must** extend `BaseTest` (`src/base_test.py`).

### What `BaseTest` provides

| Provided | Detail |
|---|---|
| `publish(counter, length)` | Build and send an echo message; record send timestamp |
| `handle_message(command, decoded_data)` | Dispatch on command ID: ECHO → latency, STATISTICS → `_statistics_values`, TASK_STATUS → `_task_values` |
| `_calculate_test_results(...)` | Aggregate latency stats (avg/min/max/P95 via numpy) |
| `_write_output_to_file(path, data)` | Serialize results list to JSON |
| `_request_status_snapshot(timeout_s)` | Poll all 14 statistics + 9 task items; return `{statistics, tasks, received, complete}` |
| `_calculate_status_delta(before, after)` | Compute counter deltas between two snapshots |
| `_get_user_input(prompt, default_value)` | Prompt with default, auto-cast to `type(default_value)` |
| `_status_lock` | `threading.Lock` — always acquire before reading/writing `_statistics_values` or `_task_values` |

### Thread-safety rule

`handle_message` is called from the **processing thread**. Every write to `_statistics_values` or `_task_values` must be done inside `with self._status_lock:`. Reads of those dicts in the main thread must also be inside the lock.

---

## 5. Threading Model

```
Main thread          Processing thread       Read thread
─────────────────    ──────────────────      ────────────────
User I/O             message_queue.get()     ser.read()
test execution       COBS decode             buffer management
menu loop            command dispatch        RTS flow control
                     calls message_handler   enqueues COBS frames
```

- All threads are **daemon threads** (`daemon=True`) and use a shared `stop_event` (`threading.Event`) for cooperative shutdown.
- Python threads cannot be restarted; `set_baudrate()` creates new `Thread` objects after calling `close()`.
- Do not call blocking I/O in the processing thread. Do not call `serial.write()` from the read thread.

---

## 6. Serial Protocol

### Wire format

```
[COBS_ENCODED( payload + XOR_CHECKSUM )][0x00]
```

### Payload structure (before encoding)

```
Byte 0    Byte 1            Byte 2    Byte 3+    Last byte
─────────────────────────────────────────────────────────
ID high   ID low | CMD(5b)  length    data…      XOR checksum
```

- **Command extraction:** `data[1] & 0x1F` (5-bit command ID).
- **Checksum:** XOR of all payload bytes, computed by `checksum.calculate_checksum(data)` and appended automatically by `SerialInterface.write()`.
- **COBS framing:** encoding and decoding are handled entirely inside `SerialInterface`; modules never deal with raw COBS.

### Known command IDs (`SerialCommand` enum)

| Name | Value | Direction | Description |
|---|---|---|---|
| `ECHO_COMMAND` | 20 | TX/RX | Roundtrip echo |
| `KEY_COMMAND` | 4 | RX | Keypad event |
| `ANALOG_COMMAND` | 3 | RX | ADC reading |
| `STATISTICS_STATUS_COMMAND` | 23 | TX/RX | Error/byte counters (14 items) |
| `TASK_STATUS_COMMAND` | 24 | TX/RX | FreeRTOS task metrics (9 items) |

Add new commands to the `SerialCommand` enum only; do not hard-code integer literals.

### Header constants (defined in `base_test.py`)

| Constant | Value | Purpose |
|---|---|---|
| `HEADER_BYTES` | `0x00 0x34` | Echo message header |
| `STATISTICS_HEADER_BYTES` | `0x00 0x37` | Statistics request header |
| `TASK_HEADER_BYTES` | `0x00 0x38` | Task status request header |

---

## 7. Output Format — JSON Test Results

All test modes that produce results write a JSON array to `test_results/<timestamp>_output.json` using `BaseTest._write_output_to_file()`. Each element in the array represents one test iteration.

### Minimum required fields per iteration

```json
{
  "test": 0,
  "waiting_time": 3.0,
  "samples": 255,
  "latency_avg": 0.001234,
  "latency_min": 0.000800,
  "latency_max": 0.003200,
  "latency_p95": 0.002100,
  "jitter": false,
  "bitrate": 18360.0,
  "dropped_messages": 0
}
```

Additional fields (e.g. `baudrate`, `status_delta`, `results` list of individual latencies, `outstanding_messages`) are appended by specific test modes. `VisualizeResults` reads these optional fields with `.get()` guards, so new fields are backward-compatible as long as they are additive.

---

## 8. Buffer and Flow Control

| Constant | Value | Meaning |
|---|---|---|
| `MAX_BUFFER_SIZE` | 1024 bytes | Hard limit; packets exceeding this are discarded |
| `BUFFER_HIGH_WATER` | 768 bytes (75%) | `ser.rts = False` — device stops sending |
| `BUFFER_LOW_WATER` | 256 bytes (25%) | `ser.rts = True` — device resumes sending |

These constants are class attributes on `SerialInterface` and must not be duplicated in other modules.

---

## 9. Code Conventions

### Python version and tooling

- Target: **Python 3.14**. Use `from __future__ import annotations` at the top of every module to enable PEP 563 postponed evaluation of annotations.
- Linter/formatter: **ruff** with `select = ["ALL"]`. Run `ruff check src/ && ruff format src/` before committing. Resolve all warnings; do not suppress rules without a comment explaining why.
- Pre-commit hooks run ruff, pytest, and mutmut automatically.

### Type annotations

- Every function parameter and return type must be annotated.
- `TYPE_CHECKING` guard for imports used only in annotations:

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from collections.abc import Callable
```

### Logging

- Obtain a module-level logger: `logger = logging.getLogger(__name__)`.
- Do not use `print()` for diagnostic output; use `logger.info/debug/warning/error`.
- Use `logger.exception()` inside `except` blocks to attach the traceback automatically.

### Constants

- Application-wide tuneable values (port, baud rate, timeout, results folder) live in `const.py` only.
- Protocol constants (header bytes, status item counts, default test parameters) live in `base_test.py`.
- Buffer constants live as class attributes in `SerialInterface`.

### Threading

- Use `threading.Lock` for shared mutable state; prefer `with lock:` over `lock.acquire()/release()`.
- Use `threading.Event` for stop signals.
- Name daemon threads explicitly for easier debugging.

---

## 10. Testing Requirements

Every new module or function must have a corresponding test file `tests/test_<module_name>.py`.

### Mandatory patterns

```python
# Hardware mocking — never open a real serial port in tests
from unittest.mock import MagicMock, patch

@pytest.fixture
def serial_interface():
    mock = MagicMock(spec=SerialInterface)
    mock.is_open.return_value = True
    return mock
```

- Mock `SerialInterface` for all tests that exercise test-mode classes.
- Use `unittest.mock.patch` for `time.perf_counter`, `time.sleep`, and file I/O where determinism matters.
- Use `tests/conftest.py` for shared fixtures (matplotlib Agg backend is already forced there).
- Tests must pass under `pytest` with coverage (configured via `pytest.ini`).

### Mutation testing targets

`mutmut` is configured to target: `application_manager`, `checksum`, `visualize_results`. When adding a significant new module, add it to the mutmut target list in the pre-commit config.

---

## 11. Dependency Graph (import direction)

```
main.py
└── application_manager.py
    ├── serial_interface.py ──► checksum.py
    │                       ──► logger_config.py
    ├── base_test.py ────────► serial_interface.py
    ├── latency_test.py ─────► base_test.py
    ├── baud_rate_test.py ───► base_test.py, latency_test.py
    ├── status_mode.py ──────► base_test.py (partially), serial_interface.py
    ├── command_mode.py ─────► serial_interface.py
    ├── regression_test.py ──► serial_interface.py
    └── visualize_results.py (no serial dependency)
```

**Rules:**
- `serial_interface.py` must not import from any test-mode module.
- `base_test.py` must not import from any concrete test-mode module.
- `const.py` must not import from any other project module.
- Circular imports are forbidden; use `TYPE_CHECKING` guards when an annotation-only import would create a cycle.

---

## 12. Connection Lifecycle

```
ApplicationManager.initialize()
  │
  ├─ Build requires_serial=False modules (e.g. VisualizeResults)
  ├─ connect_serial()
  │    ├─ SerialInterface.open()
  │    ├─ set_message_handler(self.handle_message)
  │    ├─ start_reading()          # spawns read + processing threads
  │    └─ Build requires_serial=True modules
  └─ Start monitor thread (polls every 0.5 s)

On disconnect (user action or cable pull):
  disconnect_serial()
    ├─ SerialInterface.close()    # sets stop_event, joins threads
    ├─ Pop serial-dependent modules from self.modules
    └─ Set mode = Mode.IDLE
```

Modules must not cache a reference to `SerialInterface.ser` directly; they receive the `SerialInterface` instance and call its public API.

---

## 13. Checklist for New Features

Before submitting a new test mode or protocol extension:

- [ ] New `Mode` value added to the `Mode` enum.
- [ ] `ModuleConfig` entry appended to `module_configs` in `ApplicationManager.__init__`.
- [ ] Module class extends `BaseTest` if it communicates with the device.
- [ ] Module class has `execute_<verb>(self) -> None` as the runner entry point.
- [ ] Module class has `handle_message(self, command: int, decoded_data: bytes) -> None` if it receives messages.
- [ ] All shared state mutations inside `with self._status_lock:`.
- [ ] New serial commands added to `SerialCommand` enum (integer literals forbidden in handler logic).
- [ ] Results written via `_write_output_to_file()` to `test_results/`.
- [ ] Test file `tests/test_<module>.py` created with mocked `SerialInterface`.
- [ ] `ruff check src/ && ruff format src/` passes cleanly.
- [ ] `pytest` passes with no regressions.
