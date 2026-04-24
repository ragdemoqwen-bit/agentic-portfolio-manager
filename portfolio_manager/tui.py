"""Textual TUI dashboard.

Three panes:
  * Top: holdings table with quotes (auto-refreshed on demand).
  * Middle: most recent cached news.
  * Bottom: the latest saved daily brief.

The TUI deliberately avoids doing network calls on every keystroke — it only
pulls fresh data when the user presses ``r``.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

from .agent.daily_brief import DailyBriefAgent, make_summarizer, run_daily_brief
from .config import get_config
from .db import CachedNews, DailyBrief, make_session_factory
from .fx import fetch_fx_rates
from .portfolio import (
    compute_totals,
    positions_to_snapshots,
    snapshot_positions,
)
from .providers import CompositeProvider, GoogleFinanceProvider, YFinanceProvider


class PortfolioTUI(App):
    CSS = """
    Screen { layout: vertical; }
    #holdings { height: 1fr; }
    #news     { height: 12; }
    #brief    { height: 1fr; }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh quotes"),
        Binding("b", "brief", "Generate daily brief"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cfg = get_config()
        self.session_factory = make_session_factory(self.cfg.db_path)
        self.provider = CompositeProvider(providers=[YFinanceProvider(), GoogleFinanceProvider()])

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Vertical(
            DataTable(id="holdings", zebra_stripes=True),
            Horizontal(Static("", id="news"), Static("", id="brief")),
            Footer(),
        )

    def on_mount(self) -> None:
        table = self.query_one("#holdings", DataTable)
        for col in ("Ticker", "Kind", "Qty", "Price", "Day %", "Value", "P/L"):
            table.add_column(col)
        self._load_news()
        self._load_brief()
        self.action_refresh()

    # --- Actions -----------------------------------------------------------

    def action_refresh(self) -> None:
        table = self.query_one("#holdings", DataTable)
        table.clear()
        with self.session_factory() as session:
            positions = snapshot_positions(session, self.provider)
        for p in positions:
            q = p.quote
            price = f"{q.price:,.2f}" if q else "—"
            day = f"{q.day_change_pct:+.2f}%" if q and q.day_change_pct is not None else "—"
            mv = p.market_value_native
            pnl = p.pnl_native
            table.add_row(
                p.holding.ticker,
                p.holding.kind,
                f"{p.holding.quantity:g}",
                price,
                day,
                f"{mv:,.2f} {p.holding.currency}" if mv is not None else "—",
                f"{pnl:+,.2f} {p.holding.currency}" if pnl is not None else "—",
            )
        if positions:
            currencies = {p.holding.currency for p in positions} | {
                p.quote.currency for p in positions if p.quote
            }
            fx = fetch_fx_rates(list(currencies), base=self.cfg.base_ccy)
            totals = compute_totals(positions, fx)
            self.sub_title = (
                f"Value {totals.market_value:,.2f} {totals.base_ccy} | "
                f"P/L {totals.pnl:+,.2f} ({totals.pnl_pct:+.2f}%)"
            )
        else:
            self.sub_title = "No holdings"

    def action_brief(self) -> None:
        summarizer = make_summarizer(self.cfg.ollama_url, self.cfg.ollama_model)
        agent = DailyBriefAgent(
            provider=self.provider, summarizer=summarizer, base_ccy=self.cfg.base_ccy
        )
        with self.session_factory() as session:
            positions = snapshot_positions(session, self.provider)
            snapshots = positions_to_snapshots(positions)
            body = run_daily_brief(
                session=session,
                agent=agent,
                snapshots=snapshots,
                tickers=[p.holding.ticker for p in positions],
            )
        self.query_one("#brief", Static).update(Text(body))

    # --- Helpers -----------------------------------------------------------

    def _load_news(self) -> None:
        with self.session_factory() as session:
            rows = (
                session.query(CachedNews)
                .order_by(CachedNews.fetched_at.desc())
                .limit(10)
                .all()
            )
        if not rows:
            self.query_one("#news", Static).update("No cached news. Run `portfolio news`.")
            return
        lines = [f"[b]Recent news[/b] ({datetime.utcnow():%Y-%m-%d %H:%M UTC})"]
        for r in rows:
            lines.append(f"- {r.ticker}: {r.title} ({r.publisher or '?'})")
        self.query_one("#news", Static).update("\n".join(lines))

    def _load_brief(self) -> None:
        with self.session_factory() as session:
            row = session.query(DailyBrief).order_by(DailyBrief.created_at.desc()).first()
        body = row.body if row else "No brief yet. Press 'b' to generate."
        self.query_one("#brief", Static).update(Text(body))


def run_tui() -> None:  # pragma: no cover - TUI entry
    PortfolioTUI().run()
