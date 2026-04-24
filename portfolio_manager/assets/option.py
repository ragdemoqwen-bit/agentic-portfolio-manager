"""Option handler.

Equity options trade per contract of 100 underlying shares, so market value is
``quantity * price * 100``. The OCC symbol encodes underlying, expiry, type,
and strike — we parse it on demand for display purposes without hitting the
network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import AssetHandler, AssetKind

_OCC_RE = re.compile(r"^(?P<root>[A-Z\.]{1,6})(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<cp>[CP])(?P<strike>\d{8})$")


@dataclass
class ParsedOption:
    underlying: str
    expiry: str  # YYYY-MM-DD
    right: str  # "call" | "put"
    strike: float


def parse_occ(symbol: str) -> ParsedOption | None:
    m = _OCC_RE.match(symbol.strip().upper())
    if not m:
        return None
    return ParsedOption(
        underlying=m["root"],
        expiry=f"20{m['yy']}-{m['mm']}-{m['dd']}",
        right="call" if m["cp"] == "C" else "put",
        strike=int(m["strike"]) / 1000.0,
    )


class OptionHandler(AssetHandler):
    kind = AssetKind.OPTION
    multiplier = 100.0
    display_label = "Option"

    def describe_symbol(self, symbol: str) -> str:
        parsed = parse_occ(symbol)
        if not parsed:
            return symbol
        return f"{parsed.underlying} {parsed.expiry} {parsed.right.upper()} ${parsed.strike:.2f}"
