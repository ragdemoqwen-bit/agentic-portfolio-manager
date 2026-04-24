"""Bond handler.

Yahoo only exposes a limited set of bond ETFs / treasury-index tickers, so for
individual bonds the user may supply a manually entered quote price. The
handler stays interchangeable with the other asset classes — it just names
itself "Bond" for display purposes.
"""

from __future__ import annotations

from .base import AssetHandler, AssetKind


class BondHandler(AssetHandler):
    kind = AssetKind.BOND
    # Bonds quote in clean price per 100 of face value. Multiplying price by
    # face-value divided by 100 gives market value; we model that by letting
    # the user enter quantity in face-value units and a price in clean-price
    # terms, and using a 0.01 multiplier.
    multiplier = 0.01
    display_label = "Bond"
