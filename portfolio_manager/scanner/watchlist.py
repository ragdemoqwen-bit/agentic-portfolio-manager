"""YAML-backed watchlist management."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_DEFAULT_PATH = Path.home() / ".agentic-portfolio" / "scanner_watchlist.yaml"

_DEFAULT_STOCKS = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    "SPY", "QQQ", "IWM",
]


@dataclass
class OptionsConfig:
    enabled: bool = True
    min_volume: int = 100
    min_open_interest: int = 500
    dte_range: list[int] = field(default_factory=lambda: [7, 90])
    include_leaps: bool = True
    leaps_min_dte: int = 180


@dataclass
class Watchlist:
    stocks: list[str] = field(default_factory=list)
    options: OptionsConfig = field(default_factory=OptionsConfig)
    path: Path = _DEFAULT_PATH

    @classmethod
    def load(cls, path: Path | None = None) -> Watchlist:
        p = path or _DEFAULT_PATH
        if not p.exists():
            wl = cls(stocks=list(_DEFAULT_STOCKS), path=p)
            wl.save()
            return wl
        raw = yaml.safe_load(p.read_text()) or {}
        opts_raw = raw.get("options", {})
        opts = OptionsConfig(
            enabled=opts_raw.get("enabled", True),
            min_volume=opts_raw.get("min_volume", 100),
            min_open_interest=opts_raw.get("min_open_interest", 500),
            dte_range=opts_raw.get("dte_range", [7, 90]),
            include_leaps=opts_raw.get("include_leaps", True),
            leaps_min_dte=opts_raw.get("leaps_min_dte", 180),
        )
        return cls(
            stocks=[s.upper() for s in raw.get("stocks", _DEFAULT_STOCKS)],
            options=opts,
            path=p,
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "stocks": self.stocks,
            "options": {
                "enabled": self.options.enabled,
                "min_volume": self.options.min_volume,
                "min_open_interest": self.options.min_open_interest,
                "dte_range": self.options.dte_range,
                "include_leaps": self.options.include_leaps,
                "leaps_min_dte": self.options.leaps_min_dte,
            },
        }
        self.path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

    def add(self, ticker: str) -> bool:
        t = ticker.upper()
        if t in self.stocks:
            return False
        self.stocks.append(t)
        self.save()
        return True

    def remove(self, ticker: str) -> bool:
        t = ticker.upper()
        if t not in self.stocks:
            return False
        self.stocks.remove(t)
        self.save()
        return True
