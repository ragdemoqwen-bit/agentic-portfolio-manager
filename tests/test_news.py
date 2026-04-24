from datetime import datetime, timezone

from portfolio_manager.db import make_session_factory
from portfolio_manager.news import cache_news, recent_cached
from portfolio_manager.providers.base import NewsItem


def test_cache_news_dedupes(tmp_path):
    factory = make_session_factory(tmp_path / "p.db")
    items = [
        NewsItem(
            ticker="AAPL",
            title="Apple beats Q2",
            publisher="Reuters",
            link="https://example.com/1",
            published=datetime.now(timezone.utc),
            summary=None,
        ),
        NewsItem(
            ticker="AAPL",
            title="Apple beats Q2",
            publisher="Reuters",
            link="https://example.com/1",  # duplicate link
            published=datetime.now(timezone.utc),
            summary=None,
        ),
        NewsItem(
            ticker="AAPL",
            title="iPad refresh",
            publisher="Bloomberg",
            link="https://example.com/2",
            published=datetime.now(timezone.utc),
            summary=None,
        ),
    ]
    with factory() as session:
        saved = cache_news(session, {"AAPL": items})
        assert saved == 2  # duplicate skipped
        # Running again should save 0
        again = cache_news(session, {"AAPL": items})
        assert again == 0
        recent = recent_cached(session, "AAPL")
        assert len(recent) == 2
