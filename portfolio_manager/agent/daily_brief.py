"""Agentic daily-brief orchestrator.

The agent is intentionally small: it gathers today's valuation, news, and
analyst snapshots, hands everything to a ``Summarizer``, and persists the
result. Swapping the summarizer implementation is a one-line change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db import DailyBrief
from ..providers import MarketDataProvider
from .ollama_client import OllamaClient
from .summarizer import ExtractiveSummarizer, OllamaSummarizer, Summarizer

log = logging.getLogger(__name__)


@dataclass
class HoldingSnapshot:
    ticker: str
    kind: str
    quantity: float
    avg_cost: float
    currency: str
    price: float | None
    day_change_pct: float | None
    name: str | None


def _format_pct(x: float | None) -> str:
    return "—" if x is None else f"{x:+.2f}%"


def _format_ccy(x: float | None, ccy: str) -> str:
    return "—" if x is None else f"{ccy} {x:,.2f}"


def build_context(
    snapshots: list[HoldingSnapshot],
    news_by_ticker: dict[str, list],
    analyst_by_ticker: dict[str, object],
    base_ccy: str,
) -> str:
    lines: list[str] = [
        f"Portfolio daily brief — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}",
        f"Reporting currency: {base_ccy}",
        "",
        "Holdings:",
    ]
    for s in snapshots:
        lines.append(
            f"- {s.ticker} ({s.kind}, {s.currency}): "
            f"qty={s.quantity:g} cost={_format_ccy(s.avg_cost, s.currency)} "
            f"price={_format_ccy(s.price, s.currency)} day={_format_pct(s.day_change_pct)}"
            + (f" | {s.name}" if s.name else "")
        )
    lines.append("")
    lines.append("Recent headlines:")
    for t, items in news_by_ticker.items():
        if not items:
            continue
        lines.append(f"{t}:")
        for n in items[:5]:
            lines.append(f"- {n.title} ({n.publisher or 'unknown'})")
    lines.append("")
    lines.append("Analyst snapshots:")
    for t, snap in analyst_by_ticker.items():
        if not snap:
            continue
        lines.append(
            f"- {t}: rec={getattr(snap, 'recommendation', None)} "
            f"target_mean={getattr(snap, 'target_mean', None)} "
            f"n={getattr(snap, 'num_analysts', None)}"
        )
    return "\n".join(lines)


@dataclass
class DailyBriefAgent:
    provider: MarketDataProvider
    summarizer: Summarizer
    base_ccy: str = "USD"

    def run(self, snapshots: list[HoldingSnapshot], tickers: list[str]) -> str:
        news_by_ticker = {t: self.provider.get_news(t, limit=5) for t in tickers}
        analyst_by_ticker = {t: self.provider.get_analyst_snapshot(t) for t in tickers}
        ctx = build_context(snapshots, news_by_ticker, analyst_by_ticker, self.base_ccy)
        try:
            return self.summarizer.summarize(ctx)
        except Exception as exc:  # pragma: no cover - LLM backend errors
            log.warning("Primary summarizer failed (%s); falling back to extractive.", exc)
            return ExtractiveSummarizer().summarize(ctx)


def make_summarizer(ollama_url: str, model: str) -> Summarizer:
    client = OllamaClient(ollama_url, model)
    if client.available():
        return OllamaSummarizer(client)
    log.info("Ollama not available; using extractive fallback summarizer.")
    return ExtractiveSummarizer()


def run_daily_brief(
    session: Session,
    agent: DailyBriefAgent,
    snapshots: list[HoldingSnapshot],
    tickers: list[str],
) -> str:
    body = agent.run(snapshots, tickers)
    session.add(DailyBrief(body=body))
    session.commit()
    return body
