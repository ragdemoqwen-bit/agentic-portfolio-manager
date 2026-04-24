"""Mutual fund handler.

Mutual funds trade at end-of-day NAV rather than continuously, but for
portfolio-valuation purposes that just means we quote them at the latest
available price — the same interface as stocks/ETFs.
"""

from __future__ import annotations

from .base import AssetHandler, AssetKind


class MutualFundHandler(AssetHandler):
    kind = AssetKind.MUTUAL_FUND
    multiplier = 1.0
    display_label = "Mutual Fund"
