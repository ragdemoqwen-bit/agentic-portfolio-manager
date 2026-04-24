"""yfinance-backed market-data provider.

``yfinance`` is treated as the primary source because it covers all four asset
classes (equities, ETFs, mutual funds, options) across US/SG/IN listings and
exposes news + analyst recommendations through a single, well-understood API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .base import AnalystSnapshot, MarketDataProvider, NewsItem, Quote

log = logging.getLogger(__name__)


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    def __init__(self) -> None:
        try:
            import yfinance  # noqa: F401
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError("yfinance is not installed") from exc

    def _ticker(self, symbol: str):
        import yfinance as yf

        return yf.Ticker(symbol)

    def get_quote(self, ticker: str) -> Quote | None:
        try:
            t = self._ticker(ticker)
            info = t.fast_info  # fast_info avoids an extra /quoteSummary call
            price = float(info["last_price"])
            prev_close = float(info.get("previous_close") or info.get("regular_market_previous_close") or 0.0) or None
            currency = (info.get("currency") or "USD").upper()
            day_change_pct = None
            if prev_close:
                day_change_pct = (price - prev_close) / prev_close * 100.0
            name = None
            try:
                name = t.info.get("shortName") or t.info.get("longName")
            except Exception:  # pragma: no cover - network/yf errors
                pass
            return Quote(
                ticker=ticker,
                price=price,
                currency=currency,
                as_of=datetime.now(timezone.utc),
                source=self.name,
                previous_close=prev_close,
                day_change_pct=day_change_pct,
                name=name,
            )
        except Exception as exc:  # pragma: no cover - network-dependent
            log.warning("yfinance get_quote(%s) failed: %s", ticker, exc)
            return None

    def get_news(self, ticker: str, limit: int = 5) -> list[NewsItem]:
        try:
            raw = self._ticker(ticker).news or []
        except Exception as exc:  # pragma: no cover
            log.warning("yfinance get_news(%s) failed: %s", ticker, exc)
            return []
        items: list[NewsItem] = []
        for entry in raw[:limit]:
            ts = entry.get("providerPublishTime")
            published = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
            items.append(
                NewsItem(
                    ticker=ticker,
                    title=entry.get("title") or "",
                    publisher=entry.get("publisher"),
                    link=entry.get("link") or "",
                    published=published,
                    summary=entry.get("summary"),
                )
            )
        return items

    def get_analyst_snapshot(self, ticker: str) -> AnalystSnapshot | None:
        try:
            info = self._ticker(ticker).info or {}
        except Exception as exc:  # pragma: no cover
            log.warning("yfinance get_analyst_snapshot(%s) failed: %s", ticker, exc)
            return None
        if not info:
            return None
        return AnalystSnapshot(
            ticker=ticker,
            recommendation=info.get("recommendationKey"),
            target_mean=info.get("targetMeanPrice"),
            target_high=info.get("targetHighPrice"),
            target_low=info.get("targetLowPrice"),
            num_analysts=info.get("numberOfAnalystOpinions"),
        )

    def get_option_chain(self, underlying: str, expiry: str | None = None) -> dict | None:
        """Return the option chain for the underlying (calls + puts)."""
        try:
            t = self._ticker(underlying)
            expiries = t.options
            if not expiries:
                return None
            exp = expiry or expiries[0]
            chain = t.option_chain(exp)
            return {
                "expiry": exp,
                "calls": chain.calls.to_dict("records") if hasattr(chain.calls, "to_dict") else [],
                "puts": chain.puts.to_dict("records") if hasattr(chain.puts, "to_dict") else [],
            }
        except Exception as exc:  # pragma: no cover
            log.warning("yfinance get_option_chain(%s) failed: %s", underlying, exc)
            return None
