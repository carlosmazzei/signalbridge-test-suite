# Headless Runner Integration Spec (.NET / External Orchestration)

> **Audience:** engineers wiring `src/runner_cli.py` into a non-Python process
> (.NET, or any other external orchestrator) via `Process` invocation.
> **Authoritative source:** `src/runner_cli.py`. This document describes its
> observable contract (arguments, stdout, exit codes, file artifacts). It is a
> **spec, not a re-implementation** — when the CLI's behavior changes, this
> file must change in the same commit (see [Keeping this document in
> sync](#keeping-this-document-in-sync)).

## 1. Overview

`runner_cli.py` is a non-interactive entry point that runs exactly one test
mode against the SignalBridge controller and then exits. It never prompts for
input. External orchestrators (e.g. a .NET service) invoke it as a child
process, optionally stream structured progress while it runs, and read a JSON
summary once it exits.

Invocation forms (all equivalent):

```bash
uv run src/runner_cli.py --mode latency --port /dev/ttyACM0 --baudrate 921600
signalbridge-runner --mode latency --port /dev/ttyACM0 --baudrate 921600   # installed console script
python -m runner_cli --mode latency --port /dev/ttyACM0 --baudrate 921600  # module entry point
```

Supported `--mode` values: `latency`, `baud_sweep`, `stress`, `regression`.
This is the full and only set — there is no way to run multiple modes in one
process invocation. Run one process per mode.

## 2. Recommended invocation from .NET

Always pass `--output-json <path>` even when also using `--feedback-stdout`.
It is the only channel that reliably carries **every** summary field
(including `summary_file`, added after the run finishes — see
[§5](#5-stdout-contract)).

```bash
uv run src/runner_cli.py \
  --mode stress \
  --port /dev/ttyACM0 --baudrate 921600 \
  --scenarios echo_burst,mixed_command_burst \
  --feedback-stdout \
  --output-json artifacts/stress_summary.json
```

.NET-side pattern:

1. Start the process with `RedirectStandardOutput = true`.
2. If `--feedback-stdout` is set, read stdout line-by-line; each line is one
   NDJSON event (see [§6](#6-ndjson-progress-events)). Otherwise stdout emits
   exactly one JSON line at exit (see [§5](#5-stdout-contract)).
3. Wait for process exit. Check the exit code (see [§4](#4-exit-codes)).
4. Read `--output-json` for the authoritative final summary.
5. If the summary's `result_file` is non-null, read that file for the
   mode-specific detail payload (echo latencies, per-scenario verdicts, etc.)
   — see [§7](#7-result-file-envelope-format).

```csharp
var psi = new ProcessStartInfo("uv", "run src/runner_cli.py --mode stress " +
    "--scenarios echo_burst --feedback-stdout --output-json artifacts/summary.json")
{
    RedirectStandardOutput = true,
    UseShellExecute = false,
};
using var proc = Process.Start(psi)!;
string? line;
while ((line = await proc.StandardOutput.ReadLineAsync()) != null)
{
    using var doc = JsonDocument.Parse(line);
    var eventName = doc.RootElement.GetProperty("event").GetString();
    // dispatch on eventName: run_started, heartbeat, mode_started,
    // stress_progress, mode_finished, run_finished, run_failed
}
await proc.WaitForExitAsync();
var exitedCleanly = proc.ExitCode == 0; // does NOT mean the test verdict was PASS
var summary = JsonSerializer.Deserialize<RunnerSummary>(
    await File.ReadAllTextAsync("artifacts/summary.json"));
```

## 3. CLI argument reference

| Argument | Applies to | Default | Notes |
| --- | --- | --- | --- |
| `--mode` | all | *(required)* | `latency \| baud_sweep \| stress \| regression` |
| `--port` | all | `const.PORT_NAME` | Serial device path |
| `--baudrate` | all | `const.BAUDRATE` | UART baud rate |
| `--timeout` | all | `const.TIMEOUT` | Serial read timeout (s) |
| `--output-json` | all | *(none)* | Path to write the final summary JSON (see §5) |
| `--feedback-stdout` | all | off | Emit NDJSON progress events to stdout |
| `--feedback-jsonl` | all | *(none)* | Also/instead append NDJSON events to this file |
| `--feedback-interval-ms` | all | `500` | Heartbeat cadence; `0` disables heartbeats |
| `--samples` | latency, baud_sweep | `255` | Messages per iteration/baud rate |
| `--message-length` | latency, baud_sweep, regression pacing | `10` | Echo payload length (6–10 bytes) |
| `--wait-time` | latency, baud_sweep, regression | `3.0` | Post-burst settle delay (s); regression uses `max(wait_time, 0.2)` |
| `--num-times` | latency | `5` | Number of latency iterations |
| `--max-wait` / `--min-wait` | latency | `0.1` / `0.0` | Inter-message delay bounds (s) |
| `--jitter` | latency | off | Randomize delay within bounds |
| `--baud-rates` | baud_sweep | all 8 standard rates | Comma-separated, e.g. `115200,230400,921600` |
| `--stress-config` | stress | built-in default | Path to a JSON file loaded via `stress_config.load_stress_config` |
| `--scenarios` | stress | all configured scenarios | Comma-separated scenario names, e.g. `echo_burst,mixed_command_burst` |
| `--version` | all | *(none)* | Prints `runner_cli <version>` to stdout and exits `0` immediately; no test is executed. |

Run `uv run src/runner_cli.py --help` for the live, generated version of this
table — treat this document as the narrative companion, not a substitute.

## 4. Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The process ran to completion without an unhandled exception. |
| `1` | The runner itself failed (e.g. serial port failed to open, or any exception during setup/execution). A `run_failed` NDJSON event is emitted first when feedback is enabled. |

**The exit code does not reflect the test verdict.** A `stress` run whose
`overall_verdict` is `FAIL` still exits `0` — the process completed
successfully, it just observed failing traffic. Verdict must be read from the
summary/result file (see §7), never inferred from the exit code.

`regression` mode currently has no structured PASS/FAIL output at all (see
§8, Known gaps) — its exit code is `0` whenever the process itself does not
crash, regardless of whether the echoed bytes matched.

`--version` is handled by `argparse` before any mode-specific logic runs: it
always exits `0` and never emits NDJSON events or a summary file.

## 5. stdout contract

- **Without `--feedback-stdout`:** stdout emits exactly one line at process
  exit — the raw summary object (not wrapped in an envelope), e.g.:

  ```json
  {"mode": "latency", "port": "/dev/ttyACM0", "baudrate": 921600, "timeout": 0.1, "duration_s": 12.4, "result_file": "/abs/path/test_results/20260705-...-latency.json", "summary_file": "/abs/path/test_results/20260705-...-runner.json"}
  ```

- **With `--feedback-stdout`:** stdout instead emits one NDJSON event per
  line (§6). The final `run_finished` event's `summary` field contains the
  same keys **except `summary_file`**, because that key is only computed
  after the NDJSON stream closes. To get `summary_file` when using live
  feedback, use `--output-json` (recommended) or read the always-written
  `test_results/*-runner.json` envelope (§7).

- `--output-json <path>` always writes the complete final summary
  (`mode`, `port`, `baudrate`, `timeout`, `duration_s`, `result_file`,
  `summary_file`) regardless of `--feedback-stdout`, and is unaffected by
  which stdout mode is active.

## 6. NDJSON progress events

Only emitted when `--feedback-stdout` and/or `--feedback-jsonl` is set. Every
record has `event` (string) and `ts` (Unix epoch seconds, float) plus
event-specific fields.

| `event` | Emitted | Key fields |
| --- | --- | --- |
| `run_started` | once, before the mode runs | `mode`, `port`, `baudrate`, `timeout` |
| `heartbeat` | every `--feedback-interval-ms` while active (skipped if interval is `0`) | `mode`, `elapsed_s`, `bytes_sent`, `bytes_received`, `commands_sent` (dict keyed by command id), `commands_received`, plus tester-specific counters when available: `latency_sent`, `latency_received`, `scenarios_completed` |
| `mode_started` | once, mode-specific setup complete | `mode` |
| `stress_progress` | `stress` mode only, per scenario transition | `mode`, `stress_event` (`scenario_started` \| `scenario_finished`), `scenario_name`, `scenario_index`, `total_scenarios`, and on `scenario_finished`: `verdict`, `drop_ratio`, `p95_ms` |
| `mode_finished` | once, mode work complete | `mode`; `stress` mode also includes `overall_verdict` |
| `run_finished` | once, always last on success | `summary` (see §5 — omits `summary_file`) |
| `run_failed` | once, only on unhandled exception | *(no extra fields; check process exit code and stderr/logs)* |

> **Compatibility note:** `stress_progress` forwards the scenario's own event
> name under `stress_event` rather than `event`, because `event` is already
> the sink's envelope key. Do not assume `stress_progress` records reuse
> `event` for the sub-event name.

## 7. Result file envelope format

Every JSON file the suite writes under `test_results/` (including the
per-run summary file, always written regardless of `--output-json`) uses the
same envelope, from `src/result_format.py`:

```json
{
  "format_type": "stress_run",
  "format_version": 1,
  "payload": { }
}
```

| `format_type` | Written by | `payload` shape |
| --- | --- | --- |
| `runner_summary` | every `runner_cli.py` invocation | Same dict as the final stdout summary (§5), including `summary_file` (self-referential absolute path) |
| `latency_series` | `latency` and `baud_sweep` modes | List of per-iteration dicts: `test`, `waiting_time`, `samples`, `latency_avg`, `latency_min`, `latency_max`, `latency_p95`, `jitter`, `bitrate`, `dropped_messages`, `results` (raw latency samples), `outstanding_messages`, `outstanding_max`, `outstanding_final`, `status_before`/`status_after` (firmware counter snapshots), `status_delta` |
| `stress_run` | `stress` mode | `run_id`, `port`, `baudrate`, `started_at`, `ended_at`, `overall_verdict` (`PASS`\|`FAIL`\|`WARN`), `scenarios`: list of `{name, run_id, started_at, ended_at, command_profile, messages_sent, messages_received, drop_ratio, latencies_ms, p50_ms, p95_ms, p99_ms, status_delta, task_snapshot, verdict, failure_reasons, tags}` |

File naming convention (`result_format.make_result_filename`):
`YYYYMMDD-HHMMSS-<run_id>-<type>.json`, e.g.
`20260705-190142-a1b2c3d4-stress.json`. `<type>` is `latency`, `baud_sweep`,
`stress`, or `runner` for the always-written summary envelope.

Use `format_type` to dispatch parsing on the .NET side — do not infer the
schema from the filename suffix alone, since it is a convenience, not a
guarantee.

## 8. Known gaps (do not paper over these when integrating)

- **`regression` mode has no machine-readable verdict.** `RegressionTest`
  only logs `[OK]`/`[FAIL]` lines (see `src/regression_test.py`); it writes
  no result file and the runner summary's `result_file` is always `null` for
  this mode. If a .NET caller needs a pass/fail signal from regression
  today, it does not exist in the JSON contract — this must be added to
  `regression_test.py` before it can be relied on programmatically. Track
  this as a prerequisite if regression-mode automation is required.
- **Exit code carries no verdict information** (§4) — always parse the
  summary/result JSON.

## 9. Keeping this document in sync

This file is a **contract**, not incidental documentation. Whenever a change
touches the headless surface — `src/runner_cli.py` (CLI flags, stdout
behavior, exit codes, event names/fields), `src/result_format.py` (envelope
shape), or any mode's result payload (`latency_test.py`, `baud_rate_test.py`,
`stress_evaluator.py`, `regression_test.py`) — update this document in the
same change. `CLAUDE.md` links here so this expectation is visible before any
edit to those files.
