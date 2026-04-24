"""Equity (common stock) handler."""

from __future__ import annotations

from .base import AssetHandler, AssetKind


class StockHandler(AssetHandler):
    kind = AssetKind.STOCK
    multiplier = 1.0
    display_label = "Stock"
