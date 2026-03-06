"""Stress test results reporter: JSON file writer and console summary."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from rich import box
from rich.panel import Panel
from rich.table import Table

from const import TEST_RESULTS_FOLDER
from ui_console import console

if TYPE_CHECKING:
    from stress_evaluator import StressRunResult

logger = logging.getLogger(__name__)

_VERDICT_STYLE: dict[str, str] = {
    "PASS": "bold green",
    "FAIL": "bold red",
    "WARN": "bold yellow",
}
_VERDICT_ICON: dict[str, str] = {
    "PASS": "✅ PASS",
    "FAIL": "❌ FAIL",
    "WARN": "⚠️  WARN",
}


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
    table = Table(
        title=f"Stress Run  {result.run_id}",
        box=box.SIMPLE_HEAD,
        show_lines=False,
    )
    table.add_column("Scenario", style="bold", min_width=24)
    table.add_column("Sent", justify="right")
    table.add_column("Rcvd", justify="right")
    table.add_column("Drop %", justify="right")
    table.add_column("P95 ms", justify="right")
    table.add_column("Verdict", justify="center")

    for s in result.scenarios:
        drop_pct = f"{s.drop_ratio * 100:.2f}%"
        p95 = f"{s.p95_ms:.1f}"
        style = _VERDICT_STYLE.get(s.verdict, "")
        verdict_str = f"[{style}]{_VERDICT_ICON.get(s.verdict, s.verdict)}[/]"
        table.add_row(
            s.name,
            str(s.messages_sent),
            str(s.messages_received),
            drop_pct,
            p95,
            verdict_str,
        )
        for reason in s.failure_reasons:
            table.add_row(f"  [dim]└─ {reason}[/dim]", "", "", "", "", "")

    overall_style = _VERDICT_STYLE.get(result.overall_verdict, "")
    overall_icon = _VERDICT_ICON.get(result.overall_verdict, result.overall_verdict)

    meta = (
        f"Port: [cyan]{result.port}[/cyan]  "
        f"Baudrate: [cyan]{result.baudrate}[/cyan]\n"
        f"Started: [dim]{result.started_at}[/dim]   "
        f"Ended: [dim]{result.ended_at}[/dim]\n\n"
        f"Overall: [{overall_style}]{overall_icon}[/]"
    )

    console.print(Panel(meta, title="Run Info", title_align="left", padding=(0, 1)))
    console.print(table)
