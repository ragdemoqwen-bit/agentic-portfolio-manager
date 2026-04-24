"""Thin HTTP client for a locally-running Ollama server.

We intentionally avoid the ``ollama`` Python SDK so the package works even when
the SDK isn't installed — a plain ``POST /api/generate`` is all we need.
"""

from __future__ import annotations

import json
import logging

import httpx

log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=self.timeout)
            r.raise_for_status()
            return True
        except Exception as exc:
            log.info("Ollama not reachable at %s: %s", self.base_url, exc)
            return False

    def generate(self, prompt: str, system: str | None = None) -> str:
        payload: dict = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        r = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "response" in data:
            return data["response"].strip()
        # Some Ollama versions stream even with stream=False. Concatenate.
        out: list[str] = []
        for line in r.text.splitlines():
            try:
                chunk = json.loads(line)
            except ValueError:
                continue
            if "response" in chunk:
                out.append(chunk["response"])
        return "".join(out).strip()
