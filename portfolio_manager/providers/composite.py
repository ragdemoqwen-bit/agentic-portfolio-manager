"""Composite provider that falls back through an ordered list of backends."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .base import AnalystSnapshot, MarketDataProvider, NewsItem, Quote

log = logging.getLogger(__name__)


@dataclass
class CompositeProvider(MarketDataProvider):
    providers: list[MarketDataProvider]
    name: str = "composite"

    def get_quote(self, ticker: str) -> Quote | None:
        for p in self.providers:
            q = p.get_quote(ticker)
            if q is not None:
                return q
        return None

    def get_news(self, ticker: str, limit: int = 5) -> list[NewsItem]:
        for p in self.providers:
            items = p.get_news(ticker, limit=limit)
            if items:
                return items
        return []

    def get_analyst_snapshot(self, ticker: str) -> AnalystSnapshot | None:
        for p in self.providers:
            snap = p.get_analyst_snapshot(ticker)
            if snap is not None:
                return snap
        return None
