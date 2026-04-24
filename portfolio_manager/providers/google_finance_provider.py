"""Google-Finance-backed provider.

Uses the ``google-finance-scraper`` package as a best-effort secondary source so
quotes can be cross-checked against Yahoo. The package's API has historically
moved around between releases, so we probe defensively and fall back to
``None`` whenever anything goes wrong — callers rely on the composite provider
to stitch Yahoo + Google together.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone

from .base import AnalystSnapshot, MarketDataProvider, NewsItem, Quote

log = logging.getLogger(__name__)


def _run_maybe_async(fn, *args, **kwargs):
    """Call ``fn`` and, if it returned a coroutine, run it to completion."""
    result = fn(*args, **kwargs)
    if inspect.iscoroutine(result):
        try:
            return asyncio.run(result)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(result)
            finally:
                loop.close()
    return result


def _dataframe_to_dict(df) -> dict | None:
    if df is None:
        return None
    if hasattr(df, "empty"):
        if df.empty:
            return None
        try:
            return df.iloc[0].to_dict()
        except Exception:  # pragma: no cover - defensive
            return None
    return df if isinstance(df, dict) else None


# Map Yahoo-style suffix → Google Finance exchange code.
_EXCHANGE_MAP = {
    ".SI": "SGX",
    ".NS": "NSE",
    ".BO": "BOM",
}


def _to_google_symbol(ticker: str) -> str:
    """Return ``SYMBOL:EXCHANGE`` for markets Google Finance knows about."""
    t = ticker.strip().upper()
    for suffix, exch in _EXCHANGE_MAP.items():
        if t.endswith(suffix):
            return f"{t[: -len(suffix)]}:{exch}"
    # US listings don't need an exchange qualifier on Google Finance.
    return t


class GoogleFinanceProvider(MarketDataProvider):
    name = "google-finance-scraper"

    def __init__(self) -> None:
        try:
            import google_finance_scraper  # noqa: F401
        except ImportError:  # pragma: no cover - optional dependency
            self._available = False
            log.info("google-finance-scraper not installed; GoogleFinanceProvider disabled.")
        else:
            self._available = True

    def _call_scraper(self, symbol: str) -> dict | None:
        """Try the couple of public entry points this library has historically shipped.

        The current release exposes ``get_stock_data`` as an ``async`` function
        returning a ``pandas.DataFrame``; older releases shipped sync functions
        returning ``dict``. We normalise both to a plain ``dict`` so the caller
        doesn't care which version is installed.
        """
        import google_finance_scraper as gfs  # type: ignore

        for attr in ("get_stock_data", "get_quote", "get_ticker", "scrape"):
            fn = getattr(gfs, attr, None)
            if not callable(fn):
                continue
            try:
                raw = _run_maybe_async(fn, symbol)
            except Exception as exc:  # pragma: no cover - network dependent
                log.debug("google-finance-scraper.%s(%s) failed: %s", attr, symbol, exc)
                continue
            if isinstance(raw, dict):
                return raw
            normalized = _dataframe_to_dict(raw)
            if normalized:
                return normalized
        return None

    def get_quote(self, ticker: str) -> Quote | None:
        if not getattr(self, "_available", False):
            return None
        symbol = _to_google_symbol(ticker)
        data = self._call_scraper(symbol)
        if not data:
            return None
        try:
            price = float(
                data.get("price")
                or data.get("current_price")
                or data.get("regularMarketPrice")
            )
        except (TypeError, ValueError):
            return None
        currency = str(data.get("currency") or "USD").upper()
        return Quote(
            ticker=ticker,
            price=price,
            currency=currency,
            as_of=datetime.now(timezone.utc),
            source=self.name,
            previous_close=data.get("previous_close"),
            name=data.get("name") or data.get("company_name"),
        )

    def get_news(self, ticker: str, limit: int = 5) -> list[NewsItem]:  # noqa: D401
        """Google Finance scraping for news is unreliable; leave it to Yahoo."""
        return []

    def get_analyst_snapshot(self, ticker: str) -> AnalystSnapshot | None:
        return None
