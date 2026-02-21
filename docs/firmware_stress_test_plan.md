# SignalBridge Firmware Stress-Test Improvement Plan

## 1) Firmware behavior this suite must validate

Based on the controller firmware docs and command map, the target device is a dual-core RP2040 system running FreeRTOS SMP with COBS-framed UART/USB communications, 5-bit command IDs, and explicit diagnostics counters for parser, queue, checksum, and buffer failures. The firmware has both functional I/O commands and diagnostic/system commands (`PC_ECHO_CMD`, `PC_ERROR_STATUS_CMD`, `PC_TASK_STATUS_CMD`, etc.), and it exposes enough telemetry to validate robustness under load, not just nominal correctness.

### Why this matters to the test suite

The current Python suite is strongest around:

- framing/checksum properties,
- echo-based latency testing,
- manual command/status interactions,
- and visualization.

To truly "stress test" firmware robustness, the suite should systematically force contention, malformed traffic, command mix bursts, reconnection events, and long-haul endurance while asserting both host-side behavior and firmware-side telemetry deltas.

---

## 2) Current strengths in this repository

1. **Good protocol baseline checks**: property-based tests already validate checksum invariants and COBS framing reconstruction.
2. **Useful runtime metrics**: latency and baud tests already capture dropped-message counts, outstanding backlog, and firmware status snapshots before/after bursts.
3. **Threaded serial implementation with backpressure hooks**: `SerialInterface` tracks byte/command statistics and uses RTS watermark controls.
4. **Pluggable architecture**: test modes are modular and routed through `ApplicationManager`, which is a good foundation for adding dedicated stress modes.

---

## 3) Gaps that limit robustness testing today

### A. Coverage is mostly positive-path for firmware behavior

- Regression mode only checks a single echo scenario.
- There is no automated matrix for all command IDs, length boundaries, or malformed payload variants.

### B. No fault-injection harness against the protocol boundary

- Missing focused tests for:
  - bad checksums,
  - truncated COBS frames,
  - oversize payloads,
  - invalid length fields,
  - interleaved partial frames and random byte noise.

### C. No endurance / soak mode

- There is no 8h/24h stability runner producing periodic health snapshots, trend analysis, and failure stop conditions.

### D. No queue-pressure and scheduler-stress scenarios

- Firmware exposes queue and task telemetry, but tests do not purposely generate command storms that saturate decode/process/output paths while measuring recovery.

### E. No disconnect/reconnect resilience validation

- USB/UART cable pull, serial reopen races, and baud-switch transitions are not validated with deterministic pass/fail criteria.

### F. No performance budgets enforced in CI

- Existing stats are informative but not used as regression gates (e.g., "P95 latency must stay < X ms at 230400 baud").

---

## 4) Proposed comprehensive stress-test roadmap

## Phase 1 — Build a robust automated stress harness (highest ROI)

1. **Create a dedicated stress runner module** (e.g., `src/stress_test.py`) with scenario plug-ins.
2. **Define a common scenario schema** (name, duration, command profile, expected error deltas, thresholds).
3. **Add structured output** with per-scenario:
   - timestamped metrics,
   - status snapshots,
   - queue/task deltas,
   - error reasons,
   - firmware/host serial settings.
4. **Add a non-interactive CLI entrypoint** for CI and overnight runs.

### Recommended initial scenarios

- `echo_burst`: high-rate echo with controlled pacing.
- `mixed_command_burst`: randomized valid command mix (echo + status + selected output/input commands).
- `status_poll_storm`: heavy diagnostic polling to stress status command handling.
- `baud_flip`: repeated baudrate transitions with stabilization checks.
- `noise_and_recovery`: inject malformed frames then assert firmware recovers and keeps serving valid requests.

## Phase 2 — Protocol and parser fault injection

1. Add host-side frame builder utilities so tests can deliberately send:
   - valid payload + wrong checksum,
   - wrong length byte,
   - COBS packet missing delimiter,
   - delimiter-only spam,
   - max-size and over-max packets.
2. For each class, assert expected firmware counters increase (`checksum_error`, `msg_malformed_error`, `cobs_decode_error`, `buffer_overflow_error`, `unknown_cmd_error`) while valid traffic remains serviceable.
3. Add **recovery assertions**: after fault bursts, a standard echo SLA must be restored within N seconds.

## Phase 3 — Endurance and longevity

1. Implement soak tests (1h short soak in CI optional nightly, 8h/24h local lab mode).
2. Collect periodic snapshots every fixed interval:
   - latency quantiles,
   - bytes sent/received rates,
   - task percent time/high watermark trends,
   - monotonic growth of critical error counters.
3. Add plateau/drift detectors:
   - increasing dropped-message ratio,
   - creeping queue errors,
   - degrading tail latency,
   - watchdog-related indicators.

## Phase 4 — Deterministic pass/fail robustness budgets

Define firmware robustness SLOs and fail tests when violated. Example starter budgets:

- Echo success ratio >= 99.9% over 50k messages.
- `checksum_error` increase only when fault injection is active.
- `buffer_overflow_error` stays at 0 under normal max-throughput scenario.
- P95 latency remains under scenario-specific threshold.
- No unrecovered communication stall longer than 2 seconds.

Budgets should be versioned in a config file (JSON/YAML) per hardware profile.

## Phase 5 — CI/lab pipeline split

1. **Pure software CI job**:
   - unit + property tests,
   - parser/frame fuzz tests with mocked serial.
2. **Hardware-in-loop (HIL) CI job** (self-hosted runner):
   - short stress matrix (5–15 minutes),
   - artifact upload of JSON metrics and plots,
   - threshold enforcement.
3. **Nightly HIL job**:
   - longer endurance scenarios,
   - trend comparison vs previous baseline.

---

## 5) Concrete backlog (implementation-ready)

### A. New code/components

- `src/stress_test.py`: orchestrates scenarios and aggregates telemetry.
- `src/frame_fuzzer.py`: deterministic malformed frame generator.
- `src/stress_config.py`: typed scenario + threshold config loader.
- `tests/test_frame_fuzzer.py`: property and edge tests for malformed-frame generation.
- `tests/test_stress_evaluator.py`: threshold evaluator and verdict logic.

### B. Improve existing modes

- Extend `RegressionTest` into table-driven test vectors (multiple commands, lengths, malformed/valid pairs).
- Add optional percentile targets and error-counter guardrails to `LatencyTest` and `BaudRateTest` outputs.
- Add scenario tags in output JSON to simplify cross-run comparisons.

### C. Reporting/observability

- Add a summary report writer that emits:
  - scenario verdicts,
  - top regressions by metric,
  - counter deltas ranked by severity.
- Extend visualization to compare baselines over time (trend line per key metric).

### D. Reliability hardening on host side

- Add watchdog around serial read/write stall detection in stress modes.
- Add robust reconnect strategy with bounded retries and explicit scenario abort reasons.
- Add monotonic run IDs to correlate logs, JSON results, and plots.

---

## 6) Prioritized execution plan (suggested order)

1. **Week 1**: stress scenario framework + JSON schema + non-interactive runner.
2. **Week 2**: parser fault injection + recovery assertions + verdict engine.
3. **Week 3**: HIL short-matrix automation + CI artifacts + baseline thresholds.
4. **Week 4**: endurance mode + trend comparison + documented SLO budgets.

This order gives immediate robustness gains while creating a scalable path to long-running stability validation.

---

## 7) Definition of "robust firmware" for this suite

A firmware build should be considered robust when it:

1. Maintains high valid-response success under sustained mixed traffic.
2. Handles malformed/hostile traffic without lockup, watchdog reset, or persistent degradation.
3. Preserves bounded latency under throughput stress and baud transitions.
4. Recovers automatically from connection disruptions.
5. Keeps critical error counters within agreed budgets during normal operation.

This definition can become an objective release gate once thresholds are codified and enforced by HIL runs.
