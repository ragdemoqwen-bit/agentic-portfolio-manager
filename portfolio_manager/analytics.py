"""Portfolio analytics: allocation breakdowns by asset class, market, currency."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .fx import FXRates
from .portfolio import Position


@dataclass
class AllocationRow:
    label: str
    value: float
    share_pct: float


def _breakdown(positions: list[Position], fx: FXRates, key) -> list[AllocationRow]:
    buckets: dict[str, float] = defaultdict(float)
    for p in positions:
        mv_native = p.market_value_native if p.market_value_native is not None else p.cost_basis_native
        mv_base = fx.convert(mv_native, p.quote.currency if p.quote else p.holding.currency)
        buckets[key(p)] += mv_base
    total = sum(buckets.values()) or 1.0
    rows = [
        AllocationRow(label=k, value=v, share_pct=v / total * 100.0)
        for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])
    ]
    return rows


def by_asset_class(positions: list[Position], fx: FXRates) -> list[AllocationRow]:
    return _breakdown(positions, fx, key=lambda p: p.holding.kind)


def by_market(positions: list[Position], fx: FXRates) -> list[AllocationRow]:
    return _breakdown(positions, fx, key=lambda p: p.holding.market)


def by_currency(positions: list[Position], fx: FXRates) -> list[AllocationRow]:
    return _breakdown(positions, fx, key=lambda p: p.holding.currency)


def by_ticker(positions: list[Position], fx: FXRates) -> list[AllocationRow]:
    return _breakdown(positions, fx, key=lambda p: p.holding.ticker)
