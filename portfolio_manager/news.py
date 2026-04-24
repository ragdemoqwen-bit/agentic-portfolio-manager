"""News retrieval wrapper that caches results in the SQLite store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .db import CachedNews
from .providers import MarketDataProvider
from .providers.base import NewsItem


def fetch_news(
    provider: MarketDataProvider,
    tickers: list[str],
    limit_per_ticker: int = 5,
) -> dict[str, list[NewsItem]]:
    out: dict[str, list[NewsItem]] = {}
    for t in tickers:
        out[t] = provider.get_news(t, limit=limit_per_ticker)
    return out


def cache_news(session: Session, news: dict[str, list[NewsItem]]) -> int:
    """Insert new headlines into the cache, skipping duplicates by (ticker, link)."""
    count = 0
    for ticker, items in news.items():
        for item in items:
            exists = session.query(CachedNews).filter_by(ticker=ticker, link=item.link).first()
            if exists:
                continue
            session.add(
                CachedNews(
                    ticker=ticker,
                    title=item.title,
                    publisher=item.publisher,
                    link=item.link,
                    published=item.published,
                    summary=item.summary,
                )
            )
            count += 1
    session.commit()
    return count


def recent_cached(session: Session, ticker: str, within_hours: int = 48) -> list[CachedNews]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    q = (
        session.query(CachedNews)
        .filter(CachedNews.ticker == ticker)
        .filter((CachedNews.published.is_(None)) | (CachedNews.published >= cutoff))
        .order_by(CachedNews.fetched_at.desc())
    )
    return list(q)
