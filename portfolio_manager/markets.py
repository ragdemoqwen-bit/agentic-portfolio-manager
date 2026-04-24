"""Ticker → (market, currency) normalization.

The package targets three markets — USA, Singapore, India — so symbol handling
stays deliberately small. Extending to a new market is a one-line change below.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Market(str, Enum):
    USA = "USA"
    SINGAPORE = "SG"
    INDIA_NSE = "IN-NSE"
    INDIA_BSE = "IN-BSE"


@dataclass(frozen=True)
class MarketInfo:
    market: Market
    currency: str
    suffix: str  # empty for USA


_SUFFIX_TO_INFO: dict[str, MarketInfo] = {
    ".SI": MarketInfo(Market.SINGAPORE, "SGD", ".SI"),
    ".NS": MarketInfo(Market.INDIA_NSE, "INR", ".NS"),
    ".BO": MarketInfo(Market.INDIA_BSE, "INR", ".BO"),
}

_USA_INFO = MarketInfo(Market.USA, "USD", "")


def classify_ticker(ticker: str) -> MarketInfo:
    """Return the market + reporting currency for a Yahoo-style ticker.

    Unsuffixed tickers are treated as USA-listed (the Yahoo convention).
    """
    t = ticker.strip().upper()
    for suffix, info in _SUFFIX_TO_INFO.items():
        if t.endswith(suffix):
            return info
    return _USA_INFO


def is_option_symbol(ticker: str) -> bool:
    """Heuristically detect OCC-style option symbols (e.g. ``AAPL240119C00150000``).

    OCC symbols are the underlying followed by ``YYMMDD`` + ``C|P`` + 8-digit strike.
    """
    t = ticker.strip().upper()
    if len(t) < 16:
        return False
    tail = t[-15:]
    if not (tail[0:6].isdigit() and tail[6] in ("C", "P") and tail[7:].isdigit()):
        return False
    return True
