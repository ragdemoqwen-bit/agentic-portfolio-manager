"""Unit tests for the yfinance provider helpers (news + fast_info shims)."""

from __future__ import annotations

from datetime import datetime, timezone

from portfolio_manager.providers.yfinance_provider import (
    _first_float,
    _first_value,
    _normalize_news_entry,
)


def test_normalize_news_nested_yahoo_schema():
    entry = {
        "id": "abc",
        "content": {
            "title": "Apple beats Q3 estimates",
            "summary": "Revenue up 12% YoY",
            "description": "Longer description…",
            "pubDate": "2026-04-23T21:25:29Z",
            "provider": {"displayName": "Yahoo Finance"},
            "canonicalUrl": {"url": "https://finance.yahoo.com/news/aapl"},
        },
    }
    item = _normalize_news_entry("AAPL", entry)
    assert item.title == "Apple beats Q3 estimates"
    assert item.publisher == "Yahoo Finance"
    assert item.link == "https://finance.yahoo.com/news/aapl"
    assert item.summary == "Revenue up 12% YoY"
    assert item.published == datetime(2026, 4, 23, 21, 25, 29, tzinfo=timezone.utc)
    assert item.ticker == "AAPL"


def test_normalize_news_legacy_flat_schema():
    entry = {
        "title": "Legacy story",
        "publisher": "Reuters",
        "link": "https://example.com/legacy",
        "providerPublishTime": 1_700_000_000,
        "summary": "Legacy summary",
    }
    item = _normalize_news_entry("AAPL", entry)
    assert item.title == "Legacy story"
    assert item.publisher == "Reuters"
    assert item.link == "https://example.com/legacy"
    assert item.summary == "Legacy summary"
    assert item.published == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_normalize_news_handles_missing_fields():
    item = _normalize_news_entry("AAPL", {"id": "x", "content": {}})
    assert item.title == ""
    assert item.link == ""
    assert item.publisher is None
    assert item.published is None


def test_first_value_prefers_snake_then_camel():
    data = {"previousClose": 272.7, "currency": "USD"}
    assert _first_value(data, "previous_close") == 272.7
    assert _first_value(data, "currency") == "USD"


def test_first_value_skips_none_and_falls_back():
    data = {"previous_close": None, "regularMarketPreviousClose": 273.17}
    assert _first_float(data, "previous_close", "regular_market_previous_close") == 273.17


def test_first_float_returns_none_when_absent():
    assert _first_float({}, "previous_close") is None
    assert _first_float({"previousClose": 0.0}, "previous_close") is None
