"""HTTP client for local Ollama (JSON mode)."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Raised when Ollama is unreachable, times out, or returns an error."""


class OllamaClient:
    """Thin wrapper around Ollama /api/chat with format=json."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:1.5b-instruct",
        timeout_seconds: float = 60.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def is_available(self) -> bool:
        try:
            resp = self._client.get("/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.1,
    ) -> str:
        """Call Ollama chat with JSON format; return assistant content string."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        }
        try:
            resp = self._client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise OllamaError(f"Ollama timed out after {self.timeout_seconds}s") from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama unreachable: {exc}") from exc

        if resp.status_code >= 400:
            raise OllamaError(f"Ollama HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise OllamaError("Ollama returned non-JSON response envelope") from exc

        message = data.get("message") or {}
        content = message.get("content")
        if not content:
            raise OllamaError("Ollama response missing message.content")
        return str(content)
