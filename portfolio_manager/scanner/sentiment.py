"""LLM-powered sentiment analysis with multi-provider support.

Supports Ollama (local), OpenRouter, and Google Gemini.
Falls back to a keyword-based heuristic when no LLM is available.
"""

from __future__ import annotations

import json
import logging
import os
import textwrap
from dataclasses import dataclass

import httpx

from .scraper import ScrapedArticle

log = logging.getLogger(__name__)

SENTIMENT_SYSTEM = textwrap.dedent("""\
    You are a financial news sentiment analyst. Analyze the headlines provided
    and return ONLY valid JSON (no markdown fences) with this schema:
    {
      "overall_score": <float from -1.0 (very bearish) to +1.0 (very bullish)>,
      "catalyst_summary": "<1-2 sentence summary of key catalysts>",
      "headlines": [
        {
          "headline": "<text>",
          "sentiment": "bullish|bearish|neutral",
          "impact": "high|medium|low",
          "timeframe": "immediate|short-term|medium-term|long-term"
        }
      ]
    }
""")


@dataclass
class SentimentResult:
    overall_score: float  # -1.0 to +1.0
    catalyst_summary: str
    headline_scores: list[dict]
    source: str  # "ollama", "openrouter", "gemini", "heuristic"


# ---------------------------------------------------------------------------
# Keyword-based heuristic fallback
# ---------------------------------------------------------------------------

_BULLISH_KEYWORDS = {
    "upgrade", "beat", "surge", "rally", "soar", "record", "growth",
    "bullish", "outperform", "buy", "breakout", "upside", "gain",
    "strong", "positive", "profit", "revenue beat", "raise",
    "dividend", "expansion", "innovation", "ai",
}
_BEARISH_KEYWORDS = {
    "downgrade", "miss", "decline", "crash", "plunge", "sell",
    "bearish", "underperform", "cut", "loss", "negative", "weak",
    "layoff", "recall", "lawsuit", "investigation", "debt",
    "warning", "downturn", "recession", "risk",
}


def _heuristic_sentiment(headlines: list[str]) -> SentimentResult:
    if not headlines:
        return SentimentResult(0.0, "No headlines available", [], "heuristic")

    total = 0.0
    scored: list[dict] = []
    for h in headlines:
        lower = h.lower()
        bull = sum(1 for kw in _BULLISH_KEYWORDS if kw in lower)
        bear = sum(1 for kw in _BEARISH_KEYWORDS if kw in lower)
        if bull > bear:
            s = "bullish"
            score_val = min(1.0, bull * 0.3)
        elif bear > bull:
            s = "bearish"
            score_val = -min(1.0, bear * 0.3)
        else:
            s = "neutral"
            score_val = 0.0
        total += score_val
        scored.append({"headline": h, "sentiment": s, "impact": "medium", "timeframe": "short-term"})

    avg = total / len(headlines) if headlines else 0.0
    return SentimentResult(
        overall_score=round(max(-1.0, min(1.0, avg)), 2),
        catalyst_summary="Heuristic keyword analysis (no LLM available)",
        headline_scores=scored,
        source="heuristic",
    )


# ---------------------------------------------------------------------------
# LLM-based analysis
# ---------------------------------------------------------------------------

def _build_prompt(ticker: str, headlines: list[str]) -> str:
    hl_text = "\n".join(f"- {h}" for h in headlines[:20])
    return f"Analyze the following financial news headlines for {ticker}:\n\n{hl_text}"


def _parse_llm_response(raw: str, source: str) -> SentimentResult:
    """Extract JSON from LLM response, handling markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
    try:
        data = json.loads(text)
        return SentimentResult(
            overall_score=float(data.get("overall_score", 0.0)),
            catalyst_summary=data.get("catalyst_summary", ""),
            headline_scores=data.get("headlines", []),
            source=source,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log.warning("Failed to parse LLM sentiment response: %s", exc)
        return SentimentResult(0.0, f"LLM response unparseable ({source})", [], source)


def _try_ollama(ticker: str, headlines: list[str]) -> SentimentResult | None:
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    try:
        r = httpx.get(f"{url}/api/tags", timeout=5)
        r.raise_for_status()
    except Exception:
        return None

    prompt = _build_prompt(ticker, headlines)
    payload = {"model": model, "prompt": prompt, "system": SENTIMENT_SYSTEM, "stream": False}
    try:
        r = httpx.post(f"{url}/api/generate", json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        raw = data.get("response", "")
        return _parse_llm_response(raw, "ollama")
    except Exception as exc:
        log.warning("Ollama sentiment failed: %s", exc)
        return None


def _try_openrouter(ticker: str, headlines: list[str]) -> SentimentResult | None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    model = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3-8b-instruct")
    prompt = _build_prompt(ticker, headlines)
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SENTIMENT_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=60,
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
        return _parse_llm_response(raw, "openrouter")
    except Exception as exc:
        log.warning("OpenRouter sentiment failed: %s", exc)
        return None


def _try_gemini(ticker: str, headlines: list[str]) -> SentimentResult | None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    prompt = f"{SENTIMENT_SYSTEM}\n\n{_build_prompt(ticker, headlines)}"
    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_llm_response(raw, "gemini")
    except Exception as exc:
        log.warning("Gemini sentiment failed: %s", exc)
        return None


def analyze_sentiment(
    ticker: str,
    articles: list[ScrapedArticle],
    yahoo_headlines: list[str] | None = None,
) -> SentimentResult:
    """Run sentiment analysis using the first available LLM provider.

    Provider priority: Ollama → OpenRouter → Gemini → heuristic fallback.
    """
    headlines = [a.headline for a in articles]
    if yahoo_headlines:
        headlines.extend(yahoo_headlines)
    if not headlines:
        return SentimentResult(0.0, "No headlines to analyze", [], "none")

    # Try LLM providers in order
    for provider_fn in (_try_ollama, _try_openrouter, _try_gemini):
        result = provider_fn(ticker, headlines)
        if result is not None:
            return result

    # Fallback
    return _heuristic_sentiment(headlines)
