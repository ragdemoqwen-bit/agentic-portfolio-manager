"""Typer-based CLI entry point."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import typer
from rich.console import Console

from . import analytics, assets
from .agent.daily_brief import DailyBriefAgent, make_summarizer, run_daily_brief
from .config import get_config
from .db import DailyBrief, make_session_factory
from .formatting import allocation_table, analyst_table, holdings_table, totals_table
from .fx import fetch_fx_rates
from .markets import classify_ticker
from .news import cache_news, fetch_news
from .portfolio import (
    add_holding,
    compute_totals,
    list_holdings,
    positions_to_snapshots,
    remove_holding,
    snapshot_positions,
)
from .providers import CompositeProvider, GoogleFinanceProvider, YFinanceProvider

log = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    help="Agentic portfolio manager — stocks / ETFs / mutual funds / bonds / options across US, SG, IN markets.",
    no_args_is_help=True,
)

console = Console()


def _make_provider() -> CompositeProvider:
    providers = [YFinanceProvider(), GoogleFinanceProvider()]
    return CompositeProvider(providers=providers)


def _make_session():
    cfg = get_config()
    return make_session_factory(cfg.db_path)()


@app.command("add")
def cmd_add(
    ticker: str = typer.Argument(..., help="Yahoo-style symbol (e.g. AAPL, D05.SI, RELIANCE.NS)."),
    qty: float = typer.Option(..., "--qty", help="Quantity. For bonds: face value units. For options: contracts."),
    cost: float = typer.Option(..., "--cost", help="Average cost price per unit in the listing currency."),
    kind: str = typer.Option(None, "--kind", help="Override asset class: stock|etf|mutual_fund|bond|option."),
    notes: str = typer.Option(None, "--notes"),
) -> None:
    """Add (or top-up) a holding."""
    with _make_session() as session:
        holding = add_holding(session, ticker=ticker, quantity=qty, avg_cost=cost, kind=kind, notes=notes)
        info = classify_ticker(holding.ticker)
        console.print(
            f"[green]Added[/green] {holding.ticker} ({holding.kind}) "
            f"qty={holding.quantity:g} avg_cost={holding.avg_cost:.4f} "
            f"{info.currency} on {info.market.value}"
        )


@app.command("remove")
def cmd_remove(
    ticker: str,
    qty: float = typer.Option(None, "--qty", help="If omitted, removes the entire position."),
) -> None:
    """Remove (or reduce) a holding."""
    with _make_session() as session:
        remove_holding(session, ticker=ticker, quantity=qty)
        console.print(f"[yellow]Removed[/yellow] {qty if qty is not None else 'all'} of {ticker}")


@app.command("list")
def cmd_list() -> None:
    """Show current holdings (no network calls)."""
    with _make_session() as session:
        holdings = list_holdings(session)
    if not holdings:
        console.print("[dim]No holdings yet — try `portfolio add AAPL --qty 10 --cost 150`.[/dim]")
        return
    from rich.table import Table
    table = Table(title="Holdings")
    for col in ("Ticker", "Kind", "Market", "Qty", "Avg Cost", "Currency", "Notes"):
        table.add_column(col)
    for h in holdings:
        table.add_row(
            h.ticker,
            h.kind,
            h.market,
            f"{h.quantity:g}",
            f"{h.avg_cost:,.4f}",
            h.currency,
            h.notes or "",
        )
    console.print(table)


@app.command("refresh")
def cmd_refresh() -> None:
    """Pull the latest quotes for every holding."""
    provider = _make_provider()
    with _make_session() as session:
        positions = snapshot_positions(session, provider)
    if not positions:
        console.print("[dim]No holdings to refresh.[/dim]")
        return
    console.print(holdings_table(positions))


@app.command("value")
def cmd_value() -> None:
    """Show the portfolio's current value in the reporting currency."""
    cfg = get_config()
    provider = _make_provider()
    with _make_session() as session:
        positions = snapshot_positions(session, provider)
    if not positions:
        console.print("[dim]No holdings yet.[/dim]")
        return
    currencies = {p.holding.currency for p in positions} | {
        p.quote.currency for p in positions if p.quote
    }
    fx = fetch_fx_rates(list(currencies), base=cfg.base_ccy)
    totals = compute_totals(positions, fx)
    console.print(holdings_table(positions))
    console.print(totals_table(totals))


@app.command("news")
def cmd_news(limit: int = typer.Option(5, "--limit", "-n")) -> None:
    """Fetch and cache news for every holding."""
    provider = _make_provider()
    with _make_session() as session:
        tickers = [h.ticker for h in list_holdings(session)]
        news = fetch_news(provider, tickers, limit_per_ticker=limit)
        saved = cache_news(session, news)
    for t, items in news.items():
        if not items:
            continue
        console.print(f"[bold]{t}[/bold]")
        for n in items:
            when = n.published.strftime("%Y-%m-%d %H:%M") if n.published else "—"
            console.print(f"  [{when}] {n.title} [dim]({n.publisher or '?'})[/dim]")
            if n.link:
                console.print(f"    {n.link}")
    console.print(f"[dim]Cached {saved} new headlines.[/dim]")


_SAVE_TO_OPT = typer.Option(None, "--save-to", help="Write the brief to a file as well.")


@app.command("brief")
def cmd_brief(save_to: Path = _SAVE_TO_OPT) -> None:
    """Produce the agentic daily brief."""
    cfg = get_config()
    provider = _make_provider()
    summarizer = make_summarizer(cfg.ollama_url, cfg.ollama_model)
    agent = DailyBriefAgent(provider=provider, summarizer=summarizer, base_ccy=cfg.base_ccy)
    with _make_session() as session:
        positions = snapshot_positions(session, provider)
        if not positions:
            console.print("[dim]No holdings — add some first with `portfolio add`.[/dim]")
            raise typer.Exit(0)
        snapshots = positions_to_snapshots(positions)
        body = run_daily_brief(
            session=session,
            agent=agent,
            snapshots=snapshots,
            tickers=[p.holding.ticker for p in positions],
        )
    console.print(body)
    if save_to:
        save_to.write_text(body)
        console.print(f"[dim]Saved brief to {save_to}[/dim]")


@app.command("briefs")
def cmd_briefs(limit: int = typer.Option(5, "--limit", "-n")) -> None:
    """List recent daily briefs stored in the database."""
    with _make_session() as session:
        rows = session.query(DailyBrief).order_by(DailyBrief.created_at.desc()).limit(limit).all()
    if not rows:
        console.print("[dim]No briefs yet. Run `portfolio brief`.[/dim]")
        return
    for row in rows:
        console.print(f"[bold]{row.created_at:%Y-%m-%d %H:%M}[/bold]\n{row.body}\n")


@app.command("assets")
def cmd_assets() -> None:
    """List supported asset classes."""
    for kind in assets.AssetKind:
        h = assets.resolve(kind.value)
        console.print(f"- {kind.value}: {h.display_label} (multiplier={h.multiplier})")


@app.command("allocation")
def cmd_allocation(
    by: str = typer.Option("asset_class", "--by", help="asset_class | market | currency | ticker"),
) -> None:
    """Show portfolio allocation breakdown."""
    cfg = get_config()
    provider = _make_provider()
    with _make_session() as session:
        positions = snapshot_positions(session, provider)
    if not positions:
        console.print("[dim]No holdings yet.[/dim]")
        return
    currencies = {p.holding.currency for p in positions} | {
        p.quote.currency for p in positions if p.quote
    }
    fx = fetch_fx_rates(list(currencies), base=cfg.base_ccy)
    dimension = (by or "asset_class").lower()
    selector = {
        "asset_class": analytics.by_asset_class,
        "kind": analytics.by_asset_class,
        "market": analytics.by_market,
        "currency": analytics.by_currency,
        "ticker": analytics.by_ticker,
    }.get(dimension)
    if selector is None:
        console.print(f"[red]Unknown --by value: {by!r}.[/red] Try asset_class / market / currency / ticker.")
        raise typer.Exit(2)
    rows = selector(positions, fx)
    console.print(allocation_table(rows, title=f"Allocation by {dimension}", base_ccy=cfg.base_ccy))


@app.command("analysts")
def cmd_analysts() -> None:
    """Show current analyst recommendations / target prices for each holding."""
    provider = _make_provider()
    with _make_session() as session:
        tickers = [h.ticker for h in list_holdings(session)]
    if not tickers:
        console.print("[dim]No holdings yet.[/dim]")
        return
    snapshots = {t: provider.get_analyst_snapshot(t) for t in tickers}
    console.print(analyst_table(snapshots))


_EXPORT_PATH_OPT = typer.Option(..., "--to", help="Path to write the CSV export.")


@app.command("export")
def cmd_export(to: Path = _EXPORT_PATH_OPT) -> None:
    """Export current holdings as a CSV file."""
    with _make_session() as session:
        holdings = list_holdings(session)
    if not holdings:
        console.print("[dim]No holdings to export.[/dim]")
        return
    with to.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "kind", "market", "quantity", "avg_cost", "currency", "notes"])
        for h in holdings:
            writer.writerow([h.ticker, h.kind, h.market, h.quantity, h.avg_cost, h.currency, h.notes or ""])
    console.print(f"[green]Exported[/green] {len(holdings)} holdings → {to}")


@app.command("tui")
def cmd_tui() -> None:
    """Launch the TUI dashboard."""
    from .tui import run_tui

    run_tui()


def main() -> None:  # pragma: no cover - CLI entry
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
