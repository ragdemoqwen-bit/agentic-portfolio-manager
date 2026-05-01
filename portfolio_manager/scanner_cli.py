"""Typer sub-commands for the opportunity scanner."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console

scanner_app = typer.Typer(
    name="scanner",
    help="Algo-trading opportunity scanner — technicals + sentiment + options.",
    no_args_is_help=True,
)

console = Console()
log = logging.getLogger(__name__)


# ---- scanner run -----------------------------------------------------------

@scanner_app.command("run")
def cmd_run(
    ticker: str | None = typer.Option(None, "--ticker", "-t", help="Scan a single ticker instead of the full watchlist."),
    min_score: float = typer.Option(60.0, "--min-score", help="Minimum composite score to surface."),
    portfolio_size: float = typer.Option(100_000.0, "--portfolio-size", help="Assumed portfolio size ($) for position sizing."),
    max_risk: float = typer.Option(5.0, "--max-risk", help="Max portfolio risk % per trade."),
    no_scrape: bool = typer.Option(False, "--no-scrape", help="Skip Playwright news scraping."),
    export: str | None = typer.Option(None, "--export", help="Export format: json or csv."),
    output_dir: str = typer.Option(str(Path.home() / ".agentic-portfolio" / "scanner_output"), "--output-dir"),
) -> None:
    """Run the scanner now — full watchlist or a single ticker."""
    from .config import get_config
    from .db import make_session_factory
    from .scanner.engine import ScannerEngine
    from .scanner.persistence import save_opportunities
    from .scanner.report import export_csv, export_json, print_results
    from .scanner.watchlist import Watchlist

    wl = Watchlist.load()
    engine = ScannerEngine(
        watchlist=wl,
        min_score=min_score,
        portfolio_size=portfolio_size,
        max_risk_pct=max_risk,
        scrape_news=not no_scrape,
    )

    if ticker:
        console.print(f"[bold]Scanning {ticker.upper()}...[/bold]")
        opps = engine.scan_ticker(ticker.upper())
    else:
        console.print(f"[bold]Scanning {len(wl.stocks)} tickers...[/bold]")
        opps = engine.scan_all()

    # Persist to DB
    cfg = get_config()
    session_factory = make_session_factory(cfg.db_path)
    with session_factory() as session:
        saved = save_opportunities(session, opps)
        console.print(f"[dim]Saved {saved} opportunities to database.[/dim]")

    # Print results
    print_results(opps, console)

    # Export if requested
    if export:
        out_path = Path(output_dir)
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if export.lower() == "json":
            export_json(opps, out_path / f"scan_{ts}.json")
            console.print(f"[green]Exported to {out_path / f'scan_{ts}.json'}[/green]")
        elif export.lower() == "csv":
            export_csv(opps, out_path / f"scan_{ts}.csv")
            console.print(f"[green]Exported to {out_path / f'scan_{ts}.csv'}[/green]")


# ---- scanner watchlist -----------------------------------------------------

watchlist_app = typer.Typer(
    name="watchlist",
    help="Manage the scanner watchlist.",
    no_args_is_help=True,
)
scanner_app.add_typer(watchlist_app, name="watchlist")


@watchlist_app.command("show")
def cmd_watchlist_show() -> None:
    """Display the current watchlist."""
    from .scanner.watchlist import Watchlist

    wl = Watchlist.load()
    console.print("[bold]Stocks:[/bold]")
    for t in wl.stocks:
        console.print(f"  {t}")
    console.print()
    console.print("[bold]Options config:[/bold]")
    console.print(f"  Enabled:        {wl.options.enabled}")
    console.print(f"  DTE range:      {wl.options.dte_range}")
    console.print(f"  Include LEAPS:  {wl.options.include_leaps}")
    console.print(f"  Min volume:     {wl.options.min_volume}")
    console.print(f"  Min OI:         {wl.options.min_open_interest}")


@watchlist_app.command("add")
def cmd_watchlist_add(
    tickers: list[str] = typer.Argument(..., help="Ticker(s) to add."),  # noqa: B008
) -> None:
    """Add ticker(s) to the watchlist."""
    from .scanner.watchlist import Watchlist

    wl = Watchlist.load()
    for t in tickers:
        if wl.add(t):
            console.print(f"[green]Added {t.upper()}[/green]")
        else:
            console.print(f"[yellow]{t.upper()} already in watchlist[/yellow]")


@watchlist_app.command("remove")
def cmd_watchlist_remove(
    tickers: list[str] = typer.Argument(..., help="Ticker(s) to remove."),  # noqa: B008
) -> None:
    """Remove ticker(s) from the watchlist."""
    from .scanner.watchlist import Watchlist

    wl = Watchlist.load()
    for t in tickers:
        if wl.remove(t):
            console.print(f"[yellow]Removed {t.upper()}[/yellow]")
        else:
            console.print(f"[dim]{t.upper()} not in watchlist[/dim]")


# ---- scanner opportunities ------------------------------------------------

@scanner_app.command("opportunities")
def cmd_opportunities(
    ticker: str | None = typer.Option(None, "--ticker", "-t"),
    min_score: float = typer.Option(0.0, "--min-score"),
    limit: int = typer.Option(50, "--limit", "-n"),
    export: str | None = typer.Option(None, "--export", help="Export format: json or csv."),
    output_dir: str = typer.Option(str(Path.home() / ".agentic-portfolio" / "scanner_output"), "--output-dir"),
) -> None:
    """View previously saved scan opportunities."""
    from .config import get_config
    from .db import make_session_factory
    from .scanner.persistence import load_opportunities
    from .scanner.report import export_csv, export_json, print_results

    cfg = get_config()
    session_factory = make_session_factory(cfg.db_path)
    with session_factory() as session:
        opps = load_opportunities(session, ticker=ticker, min_score=min_score, limit=limit)

    if not opps:
        console.print("[dim]No saved opportunities found. Run 'portfolio scanner run' first.[/dim]")
        return

    print_results(opps, console)

    if export:
        out_path = Path(output_dir)
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if export.lower() == "json":
            export_json(opps, out_path / f"history_{ts}.json")
            console.print(f"[green]Exported to {out_path / f'history_{ts}.json'}[/green]")
        elif export.lower() == "csv":
            export_csv(opps, out_path / f"history_{ts}.csv")
            console.print(f"[green]Exported to {out_path / f'history_{ts}.csv'}[/green]")


# ---- scanner schedule ------------------------------------------------------

@scanner_app.command("schedule")
def cmd_schedule(
    cron: str = typer.Option("0 1 * * 1-5", "--cron", help="Cron expression (5 fields: min hour day month dow)."),
    tz: str = typer.Option("UTC", "--tz", help="Timezone for the schedule."),
) -> None:
    """Start the overnight scheduler (foreground process)."""
    from .scanner.scheduler import start_scheduler

    start_scheduler(cron_expr=cron, timezone=tz)
