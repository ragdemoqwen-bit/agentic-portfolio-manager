"""Asset-class base interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AssetKind(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    BOND = "bond"
    OPTION = "option"


@dataclass
class ValuationContext:
    quantity: float
    price: float
    currency: str


class AssetHandler:
    """Base class — subclasses customize lot-size / multiplier behaviour."""

    kind: AssetKind
    multiplier: float = 1.0
    display_label: str = ""

    def market_value(self, ctx: ValuationContext) -> float:
        return ctx.quantity * ctx.price * self.multiplier

    def describe(self) -> str:
        return self.display_label or self.kind.value
