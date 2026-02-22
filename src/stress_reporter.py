"""Stress test results reporter: JSON file writer and console summary."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from const import TEST_RESULTS_FOLDER

if TYPE_CHECKING:
    from stress_evaluator import StressRunResult

logger = logging.getLogger(__name__)

# Emoji indicators for quick scanning
_VERDICT_ICON = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "WARN": "⚠️  WARN"}


def write_json_report(
    result: StressRunResult, output_dir: str = TEST_RESULTS_FOLDER
) -> Path:
    """Write <run_id>_stress.json to *output_dir* and return the path."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{result.run_id}_stress.json"
    try:
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=4)
        logger.info("Stress report written to %s", out_path)
    except OSError:
        logger.exception("Failed to write stress report to %s", out_path)
    return out_path


def print_summary(result: StressRunResult) -> None:
    """Print a compact summary table to stdout."""
    col_w = [24, 6, 6, 8, 10, 14]
    headers = ["Scenario", "Sent", "Rcvd", "Drop %", "P95 ms", "Verdict"]
    sep = "─" * (sum(col_w) + len(col_w) * 3 + 1)

    print()
    print(f"  Stress Run  {result.run_id}")
    print(f"  Port: {result.port}  Baudrate: {result.baudrate}")
    print(f"  Started: {result.started_at}   Ended: {result.ended_at}")
    print(sep)
    header_line = " │ ".join(h.ljust(w) for h, w in zip(headers, col_w, strict=False))
    print(f" {header_line}")
    print(sep)

    for s in result.scenarios:
        drop_pct = f"{s.drop_ratio * 100:.2f}%"
        p95 = f"{s.p95_ms:.1f}"
        verdict_str = _VERDICT_ICON.get(s.verdict, s.verdict)
        row = [
            s.name,
            str(s.messages_sent),
            str(s.messages_received),
            drop_pct,
            p95,
            verdict_str,
        ]
        row_line = " │ ".join(v.ljust(w) for v, w in zip(row, col_w, strict=False))
        print(f" {row_line}")
        for reason in s.failure_reasons:
            print(f"   └─ {reason}")

    print(sep)
    overall = _VERDICT_ICON.get(result.overall_verdict, result.overall_verdict)
    print(f"  Overall: {overall}")
    print()
