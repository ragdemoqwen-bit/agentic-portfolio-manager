"""FX conversion with a small in-memory cache.

Uses Yahoo FX pairs via ``yfinance`` (e.g. ``SGDUSD=X``). The cache lives for
the lifetime of a process; refreshes are triggered by callers, not by time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class FXRates:
    base: str = "USD"
    rates: dict[str, float] = field(default_factory=dict)

    def convert(self, amount: float, from_ccy: str, to_ccy: str | None = None) -> float:
        target = (to_ccy or self.base).upper()
        src = from_ccy.upper()
        if src == target:
            return amount
        # All rates are stored as CCY->base. To go A -> B: amount * (A->base) / (B->base).
        a = self._rate_to_base(src)
        b = self._rate_to_base(target)
        if a is None or b is None or b == 0:
            return amount  # best-effort: leave unchanged
        return amount * a / b

    def _rate_to_base(self, ccy: str) -> float | None:
        ccy = ccy.upper()
        if ccy == self.base.upper():
            return 1.0
        return self.rates.get(ccy)


def fetch_fx_rates(currencies: list[str], base: str = "USD") -> FXRates:
    """Fetch rates for each currency → ``base`` via ``yfinance``.

    Currencies already equal to ``base`` are skipped. Failed lookups are
    silently omitted; the caller then falls back to leaving amounts in their
    native currency.
    """
    import yfinance as yf

    rates: dict[str, float] = {}
    for ccy in {c.upper() for c in currencies if c}:
        if ccy == base.upper():
            continue
        pair = f"{ccy}{base}=X"
        try:
            fi = yf.Ticker(pair).fast_info
            price = float(fi["last_price"])
            if price > 0:
                rates[ccy] = price
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("FX fetch failed for %s: %s", pair, exc)
    return FXRates(base=base.upper(), rates=rates)
