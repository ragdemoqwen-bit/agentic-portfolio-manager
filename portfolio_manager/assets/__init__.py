"""Asset-class specific helpers.

All supported asset classes are resolved through a single ``resolve(kind)``
entry point so that the CLI and portfolio layer never switch on a string
directly.
"""

from __future__ import annotations

from .base import AssetHandler, AssetKind
from .bond import BondHandler
from .etf import ETFHandler
from .mutual_fund import MutualFundHandler
from .option import OptionHandler
from .stock import StockHandler

_HANDLERS: dict[str, AssetHandler] = {
    AssetKind.STOCK: StockHandler(),
    AssetKind.ETF: ETFHandler(),
    AssetKind.MUTUAL_FUND: MutualFundHandler(),
    AssetKind.BOND: BondHandler(),
    AssetKind.OPTION: OptionHandler(),
}


def resolve(kind: str) -> AssetHandler:
    try:
        return _HANDLERS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown asset kind: {kind!r}") from exc


__all__ = [
    "AssetHandler",
    "AssetKind",
    "StockHandler",
    "ETFHandler",
    "MutualFundHandler",
    "BondHandler",
    "OptionHandler",
    "resolve",
]
