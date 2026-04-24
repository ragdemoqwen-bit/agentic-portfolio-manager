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


def _first_value(mapping, *keys):
    """Return the first non-None value from ``mapping`` for any of ``keys``.

    ``yfinance.fast_info`` keys can be either ``snake_case`` or ``camelCase``
    depending on version — bracket access fuzzy-matches but ``.get`` does not,
    so we try both styles explicitly.
    """
    for k in keys:
        for candidate in (k, _to_camel(k)):
            try:
                v = mapping[candidate]
            except (KeyError, TypeError):
                v = None
            if v is not None:
                return v
    return None


def _first_float(mapping, *keys) -> float | None:
    v = _first_value(mapping, *keys)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f or None


def _to_camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def _normalize_news_entry(ticker: str, entry: dict) -> NewsItem:
    """Parse both legacy-flat and ``{id, content}``-nested Yahoo news payloads."""
    content = entry.get("content") if isinstance(entry, dict) else None
    src = content if isinstance(content, dict) else entry

    title = src.get("title") or ""
    summary = src.get("summary") or src.get("description")

    provider_obj = src.get("provider")
    publisher = (
        provider_obj.get("displayName") if isinstance(provider_obj, dict) else provider_obj
    ) or src.get("publisher")

    link = _extract_link(src)

    published = _parse_published(src)

    return NewsItem(
        ticker=ticker,
        title=title,
        publisher=publisher,
        link=link or "",
        published=published,
        summary=summary,
    )


def _extract_link(src: dict) -> str | None:
    for key in ("canonicalUrl", "clickThroughUrl"):
        url_obj = src.get(key)
        if isinstance(url_obj, dict) and url_obj.get("url"):
            return url_obj["url"]
    return src.get("link") or src.get("url")


def _parse_published(src: dict) -> datetime | None:
    ts = src.get("providerPublishTime")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    for key in ("pubDate", "displayTime"):
        raw = src.get(key)
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


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
            prev_close = _first_float(info, "previous_close", "regular_market_previous_close")
            currency = str(_first_value(info, "currency") or "USD").upper()
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
            items.append(_normalize_news_entry(ticker, entry))
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
