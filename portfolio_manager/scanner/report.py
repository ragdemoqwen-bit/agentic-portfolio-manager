"""Rich CLI reporting and JSON/CSV export for scanner opportunities."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .opportunities import Opportunity

log = logging.getLogger(__name__)


def _direction_color(direction: str) -> str:
    return "green" if direction == "LONG" else "red"


def opportunity_panel(opp: Opportunity) -> Panel:
    """Build a Rich Panel for a single opportunity."""
    color = _direction_color(opp.direction.value)
    lines: list[str] = [
        f"[bold]Score:[/bold]        {opp.score:.0f} / 100",
        f"[bold]Direction:[/bold]    [{color}]{opp.direction.value}[/{color}]",
        f"[bold]Instrument:[/bold]   {opp.instrument.value}",
        f"[bold]Strategy:[/bold]     {opp.strategy}",
        f"[bold]Timeframe:[/bold]    {opp.timeframe}",
        "",
        f"[bold]Entry Price:[/bold]  ${opp.entry_price:,.2f}",
        f"[bold]Target:[/bold]       ${opp.target_price:,.2f}",
        f"[bold]Stop Loss:[/bold]    ${opp.stop_loss:,.2f}",
        f"[bold]Risk/Reward:[/bold]  1 : {opp.risk_reward:.2f}",
        "",
        f"[bold]Risk/Unit:[/bold]    ${opp.risk_per_unit:,.2f}",
        f"[bold]Suggested Qty:[/bold] {opp.suggested_qty}",
        f"[bold]Max Loss:[/bold]     ${opp.max_loss:,.2f}",
        f"[bold]Portfolio Risk:[/bold] {opp.portfolio_risk_pct:.1f}%",
        "",
        f"[bold]Technicals:[/bold]   {opp.technical_summary}",
        f"[bold]Sentiment:[/bold]    {opp.sentiment_summary}",
        f"[bold]Catalysts:[/bold]    {opp.catalysts}",
    ]
    if opp.option_detail:
        od = opp.option_detail
        lines.append("")
        exp_label = f"{od.expiration} ({od.dte}d)"
        if od.is_leap:
            exp_label += " [LEAP]"
        lines.append(f"[bold]Strike:[/bold]      ${od.strike:,.2f}  Exp: {exp_label}")
        if od.iv is not None:
            lines.append(f"[bold]IV:[/bold]          {od.iv:.1%}")
        if od.iv_rank is not None:
            lines.append(f"[bold]IV Rank:[/bold]     {od.iv_rank:.0f}th percentile")
        greeks: list[str] = []
        if od.delta is not None:
            greeks.append(f"Delta={od.delta:.2f}")
        if od.theta is not None:
            greeks.append(f"Theta={od.theta:.3f}")
        if od.vega is not None:
            greeks.append(f"Vega={od.vega:.3f}")
        if greeks:
            lines.append(f"[bold]Greeks:[/bold]      {' | '.join(greeks)}")

    if opp.wheel_candidate:
        lines.append("")
        lines.append(f"[bold yellow]Wheel:[/bold yellow]       {opp.wheel_notes}")

    lines.append("")
    lines.append(f"[dim]Scanned: {opp.scanned_at.strftime('%Y-%m-%d %H:%M UTC')}[/dim]")

    return Panel(
        "\n".join(lines),
        title=f"[bold {color}]{opp.direction.value} {opp.ticker}[/bold {color}]",
        border_style=color,
        expand=False,
    )


def opportunities_table(opps: list[Opportunity]) -> Table:
    """Summary table of all opportunities."""
    table = Table(title="Scan Results", show_lines=True)
    for col in ("Ticker", "Score", "Dir", "Instrument", "Strategy",
                "Entry", "Target", "Stop", "R:R", "Risk%"):
        justify = "left" if col in {"Ticker", "Strategy", "Instrument"} else "right"
        table.add_column(col, justify=justify)

    for o in sorted(opps, key=lambda x: x.score, reverse=True):
        color = _direction_color(o.direction.value)
        instrument_label = o.instrument.value
        if o.option_detail and o.option_detail.is_leap:
            instrument_label += " (LEAP)"
        table.add_row(
            o.ticker,
            f"{o.score:.0f}",
            Text(o.direction.value, style=color),
            instrument_label,
            o.strategy[:40],
            f"${o.entry_price:,.2f}",
            f"${o.target_price:,.2f}",
            f"${o.stop_loss:,.2f}",
            f"1:{o.risk_reward:.2f}",
            f"{o.portfolio_risk_pct:.1f}%",
        )
    return table


def _opp_to_dict(opp: Opportunity) -> dict:
    d = {
        "ticker": opp.ticker,
        "score": opp.score,
        "direction": opp.direction.value,
        "instrument": opp.instrument.value,
        "strategy": opp.strategy,
        "timeframe": opp.timeframe,
        "entry_price": opp.entry_price,
        "target_price": opp.target_price,
        "stop_loss": opp.stop_loss,
        "risk_reward": opp.risk_reward,
        "risk_per_unit": opp.risk_per_unit,
        "suggested_qty": opp.suggested_qty,
        "max_loss": opp.max_loss,
        "portfolio_risk_pct": opp.portfolio_risk_pct,
        "technical_summary": opp.technical_summary,
        "sentiment_summary": opp.sentiment_summary,
        "catalysts": opp.catalysts,
        "scanned_at": opp.scanned_at.isoformat(),
        "wheel_candidate": opp.wheel_candidate,
        "wheel_notes": opp.wheel_notes,
    }
    if opp.option_detail:
        d["option_detail"] = {
            "strike": opp.option_detail.strike,
            "expiration": opp.option_detail.expiration,
            "dte": opp.option_detail.dte,
            "premium": opp.option_detail.premium,
            "iv": opp.option_detail.iv,
            "iv_rank": opp.option_detail.iv_rank,
            "delta": opp.option_detail.delta,
            "theta": opp.option_detail.theta,
            "vega": opp.option_detail.vega,
            "is_leap": opp.option_detail.is_leap,
        }
    return d


def export_json(opps: list[Opportunity], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump([_opp_to_dict(o) for o in opps], f, indent=2)
    log.info("Exported %d opportunities to %s", len(opps), path)


def export_csv(opps: list[Opportunity], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ticker", "score", "direction", "instrument", "strategy", "timeframe",
        "entry_price", "target_price", "stop_loss", "risk_reward",
        "risk_per_unit", "suggested_qty", "max_loss", "portfolio_risk_pct",
        "technical_summary", "sentiment_summary", "catalysts", "scanned_at",
        "wheel_candidate", "wheel_notes",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for o in opps:
            row = _opp_to_dict(o)
            row.pop("option_detail", None)
            writer.writerow(row)
    log.info("Exported %d opportunities to %s", len(opps), path)


def print_results(opps: list[Opportunity], console: Console | None = None) -> None:
    """Print opportunities to the console — summary table + detail panels."""
    con = console or Console()
    if not opps:
        con.print("[dim]No opportunities found above threshold.[/dim]")
        return
    con.print(opportunities_table(opps))
    con.print()
    for opp in sorted(opps, key=lambda x: x.score, reverse=True):
        con.print(opportunity_panel(opp))
        con.print()
