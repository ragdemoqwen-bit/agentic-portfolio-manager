"""Rich-based formatting helpers shared between the CLI and TUI."""

from __future__ import annotations

from rich.table import Table

from .portfolio import PortfolioTotals, Position


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
