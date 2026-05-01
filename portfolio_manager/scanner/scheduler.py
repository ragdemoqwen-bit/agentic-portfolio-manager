"""APScheduler wrapper for overnight scanning."""

from __future__ import annotations

import logging

from rich.console import Console

from .engine import ScannerEngine
from .report import print_results

log = logging.getLogger(__name__)
console = Console()


def _scan_job() -> None:
    """Job function executed by the scheduler."""
    console.print("[bold]Starting scheduled scan...[/bold]")
    engine = ScannerEngine()
    opps = engine.scan_all()
    print_results(opps, console)
    console.print(f"[dim]Scan complete — {len(opps)} opportunities found.[/dim]")


def start_scheduler(cron_expr: str = "0 1 * * 1-5", timezone: str = "UTC") -> None:
    """Start APScheduler with a cron trigger and block.

    Default: 1:00 AM UTC, weekdays only.
    """
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    parts = cron_expr.split()
    if len(parts) != 5:
        console.print(f"[red]Invalid cron expression: {cron_expr}[/red]")
        return

    trigger = CronTrigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
        timezone=timezone,
    )

    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(_scan_job, trigger, id="scanner_overnight", replace_existing=True)

    console.print(f"[green]Scheduler started[/green] — cron: {cron_expr} ({timezone})")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("\n[yellow]Scheduler stopped.[/yellow]")
