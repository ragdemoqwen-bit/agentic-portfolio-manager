"""Runtime configuration sourced from environment variables with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_db_path() -> Path:
    return Path(os.environ.get("PORTFOLIO_DB", Path.home() / ".agentic-portfolio" / "portfolio.db"))


@dataclass(frozen=True)
class Config:
    db_path: Path
    base_ccy: str
    ollama_url: str
    ollama_model: str
    news_limit_per_ticker: int
    http_timeout: float

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            db_path=_default_db_path(),
            base_ccy=os.environ.get("PORTFOLIO_BASE_CCY", "USD").upper(),
            ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2"),
            news_limit_per_ticker=int(os.environ.get("PORTFOLIO_NEWS_LIMIT", "5")),
            http_timeout=float(os.environ.get("PORTFOLIO_HTTP_TIMEOUT", "10")),
        )


def get_config() -> Config:
    return Config.from_env()
