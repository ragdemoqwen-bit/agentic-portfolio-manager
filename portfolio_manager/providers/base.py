"""Market-data provider interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class Quote:
    ticker: str
    price: float
    currency: str
    as_of: datetime
    source: str
    previous_close: float | None = None
    day_change_pct: float | None = None
    name: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class NewsItem:
    ticker: str
    title: str
    publisher: str | None
    link: str
    published: datetime | None
    summary: str | None = None


@dataclass
class AnalystSnapshot:
    ticker: str
    recommendation: str | None  # e.g. "buy", "hold", "sell"
    target_mean: float | None
    target_high: float | None
    target_low: float | None
    num_analysts: int | None


@runtime_checkable
class MarketDataProvider(Protocol):
    name: str

    def get_quote(self, ticker: str) -> Quote | None:  # noqa: D401
        """Return a current quote for ``ticker`` or ``None`` if unavailable."""

    def get_news(self, ticker: str, limit: int = 5) -> list[NewsItem]:
        ...

    def get_analyst_snapshot(self, ticker: str) -> AnalystSnapshot | None:
        ...
