"""ETF handler."""

from __future__ import annotations

from .base import AssetHandler, AssetKind


class ETFHandler(AssetHandler):
    kind = AssetKind.ETF
    multiplier = 1.0
    display_label = "ETF"
