"""Summarizers used by the agentic daily-brief flow.

``OllamaSummarizer`` is the happy-path implementation that delegates to a local
Ollama server. ``ExtractiveSummarizer`` is a dependency-free fallback: it picks
the most relevant headlines and composes a deterministic, template-based brief
so the brief is still useful when the model isn't available (CI, offline use).
"""

from __future__ import annotations

import logging
import textwrap
from typing import Protocol

from .ollama_client import OllamaClient

log = logging.getLogger(__name__)


SYSTEM_PROMPT = textwrap.dedent(
    """
    You are a concise, level-headed portfolio analyst. Given a list of holdings,
    their recent price moves, relevant news headlines, and analyst snapshots,
    produce a SHORT daily brief for the investor. Use plain English. Be neutral
    and factual — no hype, no investment advice. Structure:

      1. One-paragraph portfolio summary (biggest gainers / losers).
      2. Per-holding bullets with the most important headline(s) + any notable
         analyst target changes.
      3. A final "What to watch" paragraph with 2-3 upcoming catalysts.
    """
).strip()


class Summarizer(Protocol):
    def summarize(self, context: str) -> str:
        ...


class OllamaSummarizer:
    def __init__(self, client: OllamaClient) -> None:
        self.client = client

    def summarize(self, context: str) -> str:
        return self.client.generate(context, system=SYSTEM_PROMPT)


class ExtractiveSummarizer:
    """Deterministic fallback that does not call an LLM."""

    def summarize(self, context: str) -> str:
        lines = [ln.strip() for ln in context.splitlines() if ln.strip()]
        headline_lines = [ln for ln in lines if ln.startswith("- ")]
        preamble = next(
            (ln for ln in lines if ln.lower().startswith(("portfolio", "holdings", "total"))),
            "Portfolio summary:",
        )
        top = headline_lines[:10]
        body = "\n".join(top) if top else "No fresh headlines fetched."
        return (
            f"{preamble}\n\n"
            "Key headlines (extractive, no LLM):\n"
            f"{body}\n\n"
            "What to watch: upcoming earnings / macro events for each holding."
        )
