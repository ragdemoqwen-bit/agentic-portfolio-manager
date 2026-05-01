"""Technical analysis strategies using pandas-ta.

Each strategy returns a TechnicalSignal with direction and confidence.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass

import pandas as pd

log = logging.getLogger(__name__)


class SignalDirection(str, enum.Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass
class TechnicalSignal:
    name: str
    direction: SignalDirection
    confidence: float  # 0.0 – 1.0
    detail: str


def _ensure_ta(df: pd.DataFrame) -> None:
    """Lazy-import pandas_ta and attach its accessor."""
    import pandas_ta  # noqa: F401 – registers .ta accessor


# ---------------------------------------------------------------------------
# Individual strategy functions
# ---------------------------------------------------------------------------

def ema_crossover(df: pd.DataFrame) -> TechnicalSignal:
    _ensure_ta(df)
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    ema20 = last.get("EMA_20")
    ema50 = last.get("EMA_50")
    ema200 = last.get("EMA_200")
    if ema20 is None or ema50 is None:
        return TechnicalSignal("EMA Crossover", SignalDirection.NEUTRAL, 0.0, "Insufficient data")

    prev_ema20 = prev.get("EMA_20", ema20)
    prev_ema50 = prev.get("EMA_50", ema50)

    if prev_ema20 <= prev_ema50 and ema20 > ema50:
        conf = 0.8 if ema200 is not None and last["Close"] > ema200 else 0.65
        return TechnicalSignal("EMA Crossover", SignalDirection.BULLISH, conf,
                               f"EMA20 crossed above EMA50; price {'above' if ema200 and last['Close'] > ema200 else 'below'} EMA200")
    if prev_ema20 >= prev_ema50 and ema20 < ema50:
        conf = 0.75
        return TechnicalSignal("EMA Crossover", SignalDirection.BEARISH, conf, "EMA20 crossed below EMA50")
    if ema20 > ema50:
        return TechnicalSignal("EMA Crossover", SignalDirection.BULLISH, 0.4, "EMA20 > EMA50 (no fresh cross)")
    return TechnicalSignal("EMA Crossover", SignalDirection.BEARISH, 0.4, "EMA20 < EMA50 (no fresh cross)")


def rsi_reversal(df: pd.DataFrame) -> TechnicalSignal:
    _ensure_ta(df)
    df.ta.rsi(length=14, append=True)
    rsi = df.iloc[-1].get("RSI_14")
    if rsi is None:
        return TechnicalSignal("RSI Reversal", SignalDirection.NEUTRAL, 0.0, "Insufficient data")
    if rsi < 30:
        return TechnicalSignal("RSI Reversal", SignalDirection.BULLISH, min(0.9, (30 - rsi) / 30 + 0.5),
                               f"RSI={rsi:.1f} — oversold")
    if rsi > 70:
        return TechnicalSignal("RSI Reversal", SignalDirection.BEARISH, min(0.9, (rsi - 70) / 30 + 0.5),
                               f"RSI={rsi:.1f} — overbought")
    return TechnicalSignal("RSI Reversal", SignalDirection.NEUTRAL, 0.3, f"RSI={rsi:.1f} — neutral range")


def macd_momentum(df: pd.DataFrame) -> TechnicalSignal:
    _ensure_ta(df)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    macd_val = last.get("MACD_12_26_9")
    signal_val = last.get("MACDs_12_26_9")
    hist = last.get("MACDh_12_26_9")
    if macd_val is None or signal_val is None:
        return TechnicalSignal("MACD Momentum", SignalDirection.NEUTRAL, 0.0, "Insufficient data")

    prev_macd = prev.get("MACD_12_26_9", macd_val)
    prev_signal = prev.get("MACDs_12_26_9", signal_val)

    if prev_macd <= prev_signal and macd_val > signal_val:
        return TechnicalSignal("MACD Momentum", SignalDirection.BULLISH, 0.75,
                               f"MACD bullish crossover; histogram={hist:.3f}")
    if prev_macd >= prev_signal and macd_val < signal_val:
        return TechnicalSignal("MACD Momentum", SignalDirection.BEARISH, 0.75,
                               f"MACD bearish crossover; histogram={hist:.3f}")
    if hist is not None and hist > 0:
        return TechnicalSignal("MACD Momentum", SignalDirection.BULLISH, 0.4,
                               f"MACD histogram positive ({hist:.3f})")
    return TechnicalSignal("MACD Momentum", SignalDirection.BEARISH, 0.4,
                           f"MACD histogram negative ({hist:.3f})" if hist else "MACD negative")


def bollinger_squeeze(df: pd.DataFrame) -> TechnicalSignal:
    _ensure_ta(df)
    df.ta.squeeze(append=True)
    last = df.iloc[-1]
    sqz_col = [c for c in df.columns if c.startswith("SQZ")]
    if not sqz_col:
        # Fallback: manual Bollinger Band check
        df.ta.bbands(length=20, std=2, append=True)
        upper = last.get("BBU_20_2.0")
        lower = last.get("BBL_20_2.0")
        mid = last.get("BBM_20_2.0")
        if upper is None or lower is None:
            return TechnicalSignal("Bollinger Squeeze", SignalDirection.NEUTRAL, 0.0, "Insufficient data")
        width = (upper - lower) / mid if mid else 0
        price = last["Close"]
        if price > upper:
            return TechnicalSignal("Bollinger Squeeze", SignalDirection.BULLISH, 0.7,
                                   f"Price broke above upper BB; width={width:.3f}")
        if price < lower:
            return TechnicalSignal("Bollinger Squeeze", SignalDirection.BEARISH, 0.7,
                                   f"Price broke below lower BB; width={width:.3f}")
        return TechnicalSignal("Bollinger Squeeze", SignalDirection.NEUTRAL, 0.3,
                               f"Price within bands; width={width:.3f}")

    # Use squeeze momentum if available
    sqz_on = last.get("SQZ_ON") if "SQZ_ON" in df.columns else None
    sqz_off = last.get("SQZ_OFF") if "SQZ_OFF" in df.columns else None
    if sqz_off and not sqz_on:
        hist_col = [c for c in df.columns if "SQZ" in c and "OSC" in c.upper()]
        if hist_col:
            osc = last.get(hist_col[0], 0)
            direction = SignalDirection.BULLISH if osc > 0 else SignalDirection.BEARISH
            return TechnicalSignal("Bollinger Squeeze", direction, 0.8,
                                   f"Squeeze released {'upward' if osc > 0 else 'downward'}")
    return TechnicalSignal("Bollinger Squeeze", SignalDirection.NEUTRAL, 0.3, "No squeeze detected")


def volume_profile(df: pd.DataFrame) -> TechnicalSignal:
    _ensure_ta(df)
    df.ta.obv(append=True)
    if "Volume" not in df.columns:
        return TechnicalSignal("Volume Profile", SignalDirection.NEUTRAL, 0.0, "No volume data")

    vol_sma = df["Volume"].rolling(20).mean()
    last_vol = df["Volume"].iloc[-1]
    avg_vol = vol_sma.iloc[-1] if not pd.isna(vol_sma.iloc[-1]) else last_vol
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0
    price_change = (df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] if len(df) >= 2 else 0

    if vol_ratio > 1.5 and price_change > 0:
        return TechnicalSignal("Volume Profile", SignalDirection.BULLISH, min(0.9, 0.5 + vol_ratio / 10),
                               f"Volume surge ({vol_ratio:.1f}x avg) with positive price action")
    if vol_ratio > 1.5 and price_change < 0:
        return TechnicalSignal("Volume Profile", SignalDirection.BEARISH, min(0.9, 0.5 + vol_ratio / 10),
                               f"Volume surge ({vol_ratio:.1f}x avg) with negative price action")
    return TechnicalSignal("Volume Profile", SignalDirection.NEUTRAL, 0.3,
                           f"Volume at {vol_ratio:.1f}x average")


def support_resistance(df: pd.DataFrame) -> TechnicalSignal:
    if len(df) < 20:
        return TechnicalSignal("Support/Resistance", SignalDirection.NEUTRAL, 0.0, "Insufficient data")

    price = df["Close"].iloc[-1]
    highs = df["High"].rolling(20).max()
    lows = df["Low"].rolling(20).min()
    recent_high = highs.iloc[-1]
    recent_low = lows.iloc[-1]

    if pd.isna(recent_high) or pd.isna(recent_low):
        return TechnicalSignal("Support/Resistance", SignalDirection.NEUTRAL, 0.0, "Insufficient data")

    price_range = recent_high - recent_low
    if price_range == 0:
        return TechnicalSignal("Support/Resistance", SignalDirection.NEUTRAL, 0.3, "No range detected")

    pct_from_low = (price - recent_low) / price_range
    pct_from_high = (recent_high - price) / price_range

    if pct_from_low < 0.15:
        return TechnicalSignal("Support/Resistance", SignalDirection.BULLISH, 0.7,
                               f"Near 20-day support ({recent_low:.2f}); bounce potential")
    if pct_from_high < 0.15:
        return TechnicalSignal("Support/Resistance", SignalDirection.BEARISH, 0.6,
                               f"Near 20-day resistance ({recent_high:.2f}); reversal risk")
    return TechnicalSignal("Support/Resistance", SignalDirection.NEUTRAL, 0.3,
                           f"Mid-range; support={recent_low:.2f}, resistance={recent_high:.2f}")


def adx_trend(df: pd.DataFrame) -> TechnicalSignal:
    _ensure_ta(df)
    df.ta.adx(length=14, append=True)
    last = df.iloc[-1]
    adx = last.get("ADX_14")
    dmp = last.get("DMP_14")
    dmn = last.get("DMN_14")
    if adx is None:
        return TechnicalSignal("ADX Trend", SignalDirection.NEUTRAL, 0.0, "Insufficient data")

    if adx < 20:
        return TechnicalSignal("ADX Trend", SignalDirection.NEUTRAL, 0.2,
                               f"ADX={adx:.1f} — weak/no trend")
    if dmp is not None and dmn is not None:
        if dmp > dmn:
            return TechnicalSignal("ADX Trend", SignalDirection.BULLISH,
                                   min(0.9, 0.4 + adx / 100),
                                   f"ADX={adx:.1f}, +DI > -DI — strong uptrend")
        return TechnicalSignal("ADX Trend", SignalDirection.BEARISH,
                               min(0.9, 0.4 + adx / 100),
                               f"ADX={adx:.1f}, -DI > +DI — strong downtrend")
    return TechnicalSignal("ADX Trend", SignalDirection.NEUTRAL, 0.3, f"ADX={adx:.1f}")


def stochastic_divergence(df: pd.DataFrame) -> TechnicalSignal:
    _ensure_ta(df)
    df.ta.stoch(k=14, d=3, smooth_k=3, append=True)
    last = df.iloc[-1]
    k = last.get("STOCHk_14_3_3")
    if k is None:
        return TechnicalSignal("Stochastic", SignalDirection.NEUTRAL, 0.0, "Insufficient data")
    if k < 20:
        return TechnicalSignal("Stochastic", SignalDirection.BULLISH, 0.65,
                               f"Stoch K={k:.1f} — oversold")
    if k > 80:
        return TechnicalSignal("Stochastic", SignalDirection.BEARISH, 0.65,
                               f"Stoch K={k:.1f} — overbought")
    return TechnicalSignal("Stochastic", SignalDirection.NEUTRAL, 0.3,
                           f"Stoch K={k:.1f} — neutral")


# ---------------------------------------------------------------------------
# Composite runner
# ---------------------------------------------------------------------------

ALL_STRATEGIES = [
    ema_crossover,
    rsi_reversal,
    macd_momentum,
    bollinger_squeeze,
    volume_profile,
    support_resistance,
    adx_trend,
    stochastic_divergence,
]


def run_technicals(df: pd.DataFrame) -> list[TechnicalSignal]:
    """Run all technical strategies on an OHLCV DataFrame."""
    signals: list[TechnicalSignal] = []
    for strategy in ALL_STRATEGIES:
        try:
            sig = strategy(df.copy())
            signals.append(sig)
        except Exception as exc:
            log.warning("Strategy %s failed: %s", strategy.__name__, exc)
            signals.append(TechnicalSignal(strategy.__name__, SignalDirection.NEUTRAL, 0.0, f"Error: {exc}"))
    return signals


def compute_technical_score(signals: list[TechnicalSignal]) -> tuple[float, SignalDirection]:
    """Combine signals into a single score (0–100) and net direction."""
    if not signals:
        return 0.0, SignalDirection.NEUTRAL

    bullish_score = 0.0
    bearish_score = 0.0
    total_weight = 0.0
    for sig in signals:
        weight = sig.confidence
        total_weight += weight
        if sig.direction == SignalDirection.BULLISH:
            bullish_score += weight
        elif sig.direction == SignalDirection.BEARISH:
            bearish_score += weight

    if total_weight == 0:
        return 0.0, SignalDirection.NEUTRAL

    net = (bullish_score - bearish_score) / total_weight
    score = abs(net) * 100
    direction = (
        SignalDirection.BULLISH if net > 0.05
        else SignalDirection.BEARISH if net < -0.05
        else SignalDirection.NEUTRAL
    )
    return min(100.0, score), direction
