"""Options-specific analysis — IV rank, unusual activity, LEAPS, and Wheel candidates."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class OptionsSignal:
    iv_rank: float | None  # 0–100
    put_call_ratio: float | None
    unusual_activity: list[dict]
    wheel_candidate: bool
    wheel_notes: str
    leaps_available: bool
    leaps_candidates: list[dict]
    score: float  # 0–100


def _compute_iv_rank(ticker_obj) -> float | None:
    """Compute IV rank = (current IV - 52w low) / (52w high - 52w low) * 100."""
    try:
        hist = ticker_obj.history(period="1y")
        if hist.empty:
            return None
        info = ticker_obj.info
        current_iv = info.get("impliedVolatility")
        if current_iv is None:
            return None
        # Approximate: use historical volatility range as proxy
        returns = hist["Close"].pct_change().dropna()
        if returns.empty:
            return None
        rolling_vol = returns.rolling(21).std() * (252 ** 0.5)
        rolling_vol = rolling_vol.dropna()
        if rolling_vol.empty:
            return None
        vol_low = rolling_vol.min()
        vol_high = rolling_vol.max()
        if vol_high == vol_low:
            return 50.0
        rank = (current_iv - vol_low) / (vol_high - vol_low) * 100
        return max(0, min(100, rank))
    except Exception as exc:
        log.debug("IV rank calc failed for %s: %s", ticker_obj.ticker, exc)
        return None


def _find_unusual_activity(chain_calls: pd.DataFrame, chain_puts: pd.DataFrame) -> list[dict]:
    """Identify strikes where volume >> open interest."""
    unusual: list[dict] = []
    for label, chain in [("call", chain_calls), ("put", chain_puts)]:
        if chain.empty:
            continue
        for _, row in chain.iterrows():
            vol = row.get("volume", 0) or 0
            oi = row.get("openInterest", 0) or 0
            if oi > 0 and vol > oi * 2 and vol > 100:
                unusual.append({
                    "type": label,
                    "strike": row.get("strike"),
                    "volume": int(vol),
                    "open_interest": int(oi),
                    "ratio": round(vol / oi, 1),
                    "implied_volatility": row.get("impliedVolatility"),
                })
    return sorted(unusual, key=lambda x: x.get("ratio", 0), reverse=True)[:5]


def _check_wheel_candidate(ticker_obj, current_price: float) -> tuple[bool, str]:
    """Check if a stock is a good Wheel strategy candidate.

    Criteria: liquid options, price > $10, stable dividend payer or blue-chip,
    not too volatile.
    """
    try:
        info = ticker_obj.info
        market_cap = info.get("marketCap", 0) or 0
        div_yield = info.get("dividendYield", 0) or 0

        notes_parts: list[str] = []
        is_candidate = True

        if current_price < 10:
            is_candidate = False
            notes_parts.append("Price too low for Wheel")
        if market_cap < 2_000_000_000:
            is_candidate = False
            notes_parts.append("Market cap < $2B")

        if is_candidate:
            if div_yield > 0:
                notes_parts.append(f"Dividend yield: {div_yield:.1%}")
            notes_parts.append(f"Market cap: ${market_cap / 1e9:.1f}B")
            notes_parts.append(
                "Sell CSPs at support → if assigned, sell covered calls → repeat"
            )

        return is_candidate, "; ".join(notes_parts)
    except Exception:
        return False, "Unable to evaluate Wheel candidacy"


def _find_leaps(ticker_obj, min_dte: int = 180) -> list[dict]:
    """Find LEAPS options (long-dated calls/puts)."""
    leaps: list[dict] = []
    try:
        expirations = ticker_obj.options
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).date()
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_date - now).days
            if dte >= min_dte:
                try:
                    chain = ticker_obj.option_chain(exp_str)
                    # Find ATM-ish calls
                    price = ticker_obj.fast_info["last_price"]
                    calls = chain.calls
                    if not calls.empty:
                        calls = calls.copy()
                        calls["dist"] = abs(calls["strike"] - price)
                        best = calls.nsmallest(2, "dist")
                        for _, row in best.iterrows():
                            leaps.append({
                                "expiration": exp_str,
                                "dte": dte,
                                "type": "call",
                                "strike": row["strike"],
                                "last_price": row.get("lastPrice"),
                                "bid": row.get("bid"),
                                "ask": row.get("ask"),
                                "iv": row.get("impliedVolatility"),
                                "volume": row.get("volume"),
                                "open_interest": row.get("openInterest"),
                            })
                except Exception as exc:
                    log.debug("LEAPS chain fetch failed for %s %s: %s", ticker_obj.ticker, exp_str, exc)
    except Exception as exc:
        log.debug("LEAPS discovery failed for %s: %s", ticker_obj.ticker, exc)
    return leaps[:6]


def analyze_options(ticker_str: str, current_price: float) -> OptionsSignal:
    """Run full options analysis for a ticker."""
    import yfinance as yf

    ticker_obj = yf.Ticker(ticker_str)

    iv_rank = _compute_iv_rank(ticker_obj)

    # Get nearest expiration chain for unusual activity + PCR
    unusual: list[dict] = []
    pcr: float | None = None
    try:
        expirations = ticker_obj.options
        if expirations:
            chain = ticker_obj.option_chain(expirations[0])
            unusual = _find_unusual_activity(chain.calls, chain.puts)
            call_vol = chain.calls["volume"].sum() if "volume" in chain.calls.columns else 0
            put_vol = chain.puts["volume"].sum() if "volume" in chain.puts.columns else 0
            pcr = put_vol / call_vol if call_vol and call_vol > 0 else None
    except Exception as exc:
        log.debug("Options chain fetch failed for %s: %s", ticker_str, exc)

    wheel_ok, wheel_notes = _check_wheel_candidate(ticker_obj, current_price)
    leaps = _find_leaps(ticker_obj)

    # Compute options score
    score = 50.0
    if iv_rank is not None:
        if iv_rank < 25:
            score += 15  # cheap options — good for buying
        elif iv_rank > 75:
            score += 10  # expensive options — good for selling premium
    if unusual:
        score += min(20, len(unusual) * 5)
    if pcr is not None and pcr > 1.2:
        score += 5  # elevated put/call — potential contrarian bullish
    if wheel_ok:
        score += 5

    return OptionsSignal(
        iv_rank=round(iv_rank, 1) if iv_rank is not None else None,
        put_call_ratio=round(pcr, 2) if pcr is not None else None,
        unusual_activity=unusual,
        wheel_candidate=wheel_ok,
        wheel_notes=wheel_notes,
        leaps_available=len(leaps) > 0,
        leaps_candidates=leaps,
        score=min(100, score),
    )
