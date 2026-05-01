"""Signal combination — merges technical, sentiment, volume, and options signals."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from .sentiment import SentimentResult
from .technical import SignalDirection, TechnicalSignal, compute_technical_score

log = logging.getLogger(__name__)


@dataclass
class CompositeSignal:
    ticker: str
    score: float  # 0–100
    direction: SignalDirection
    technical_score: float
    sentiment_score: float
    volume_score: float
    options_score: float
    technical_signals: list[TechnicalSignal]
    sentiment_result: SentimentResult | None
    strategy_label: str


def _load_weights() -> dict[str, float]:
    return {
        "technical": float(os.environ.get("SCANNER_W_TECH", "0.50")),
        "sentiment": float(os.environ.get("SCANNER_W_SENT", "0.30")),
        "volume": float(os.environ.get("SCANNER_W_VOL", "0.10")),
        "options": float(os.environ.get("SCANNER_W_OPT", "0.10")),
    }


def combine_signals(
    ticker: str,
    tech_signals: list[TechnicalSignal],
    sentiment: SentimentResult | None,
    volume_score: float = 50.0,
    options_score: float = 50.0,
) -> CompositeSignal:
    """Compute a weighted composite score from all signal sources."""
    weights = _load_weights()

    # Technical: 0–100
    tech_raw, tech_dir = compute_technical_score(tech_signals)

    # Sentiment: map -1..+1 → 0..100
    if sentiment:
        sent_normalized = (sentiment.overall_score + 1.0) / 2.0 * 100.0
    else:
        sent_normalized = 50.0

    composite = (
        weights["technical"] * tech_raw
        + weights["sentiment"] * sent_normalized
        + weights["volume"] * volume_score
        + weights["options"] * options_score
    )

    # Determine net direction from the dominant signal
    if tech_dir == SignalDirection.NEUTRAL and sentiment:
        if sentiment.overall_score > 0.2:
            net_dir = SignalDirection.BULLISH
        elif sentiment.overall_score < -0.2:
            net_dir = SignalDirection.BEARISH
        else:
            net_dir = SignalDirection.NEUTRAL
    else:
        net_dir = tech_dir

    # Build a human-readable strategy label from top signals
    top_signals = sorted(
        [s for s in tech_signals if s.direction != SignalDirection.NEUTRAL],
        key=lambda s: s.confidence,
        reverse=True,
    )[:3]
    label_parts = [s.name for s in top_signals]
    if sentiment and abs(sentiment.overall_score) > 0.3:
        tone = "Bullish" if sentiment.overall_score > 0 else "Bearish"
        label_parts.append(f"{tone} Sentiment")
    strategy_label = " + ".join(label_parts) if label_parts else "Mixed Signals"

    return CompositeSignal(
        ticker=ticker,
        score=round(min(100.0, max(0.0, composite)), 1),
        direction=net_dir,
        technical_score=round(tech_raw, 1),
        sentiment_score=round(sent_normalized, 1),
        volume_score=round(volume_score, 1),
        options_score=round(options_score, 1),
        technical_signals=tech_signals,
        sentiment_result=sentiment,
        strategy_label=strategy_label,
    )
