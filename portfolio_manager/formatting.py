"""Rich-based formatting helpers shared between the CLI and TUI."""

from __future__ import annotations

from rich.table import Table

from .analytics import AllocationRow
from .portfolio import PortfolioTotals, Position
from .providers.base import AnalystSnapshot


def holdings_table(positions: list[Position]) -> Table:
    table = Table(title="Holdings", show_lines=False)
    for col in ("Ticker", "Kind", "Market", "Qty", "Avg Cost", "Price", "Day %", "Value", "P/L"):
        table.add_column(col, justify="right" if col not in {"Ticker", "Kind", "Market"} else "left")
    for p in positions:
        q = p.quote
        price = f"{q.price:,.2f}" if q else "—"
        day = f"{q.day_change_pct:+.2f}%" if q and q.day_change_pct is not None else "—"
        mv = p.market_value_native
        pnl = p.pnl_native
        value_str = f"{mv:,.2f} {p.holding.currency}" if mv is not None else "—"
        pnl_str = f"{pnl:+,.2f} {p.holding.currency}" if pnl is not None else "—"
        table.add_row(
            p.holding.ticker,
            p.holding.kind,
            p.holding.market,
            f"{p.holding.quantity:g}",
            f"{p.holding.avg_cost:,.2f} {p.holding.currency}",
            price,
            day,
            value_str,
            pnl_str,
        )
    return table


def totals_table(totals: PortfolioTotals) -> Table:
    table = Table(title=f"Totals (base={totals.base_ccy})", show_header=False)
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Market value", f"{totals.market_value:,.2f} {totals.base_ccy}")
    table.add_row("Cost basis", f"{totals.cost_basis:,.2f} {totals.base_ccy}")
    table.add_row("Unrealized P/L", f"{totals.pnl:+,.2f} {totals.base_ccy}")
    table.add_row("Unrealized P/L %", f"{totals.pnl_pct:+.2f}%")
    return table


def allocation_table(rows: list[AllocationRow], title: str, base_ccy: str) -> Table:
    table = Table(title=title)
    table.add_column("Bucket")
    table.add_column(f"Value ({base_ccy})", justify="right")
    table.add_column("Share", justify="right")
    for r in rows:
        table.add_row(r.label, f"{r.value:,.2f}", f"{r.share_pct:5.2f}%")
    return table


def analyst_table(snapshots: dict[str, AnalystSnapshot | None]) -> Table:
    table = Table(title="Analyst snapshots")
    for col in ("Ticker", "Recommendation", "Target (mean)", "Target (low)", "Target (high)", "# Analysts"):
        table.add_column(col, justify="right" if col != "Ticker" else "left")
    for ticker, snap in snapshots.items():
        if snap is None:
            table.add_row(ticker, "—", "—", "—", "—", "—")
            continue
        table.add_row(
            ticker,
            snap.recommendation or "—",
            f"{snap.target_mean:,.2f}" if snap.target_mean is not None else "—",
            f"{snap.target_low:,.2f}" if snap.target_low is not None else "—",
            f"{snap.target_high:,.2f}" if snap.target_high is not None else "—",
            str(snap.num_analysts) if snap.num_analysts is not None else "—",
        )
    return table
