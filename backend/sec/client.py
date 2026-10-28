"""HTTP client for sec.gov with User-Agent, rate limiting, and backoff."""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from backend.sec.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 1.0


class SecClient:
    """Thin httpx wrapper that enforces SEC fair-access rules."""

    def __init__(
        self,
        user_agent: str,
        rate_limiter: Optional[RateLimiter] = None,
        max_per_second: float = 8.0,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.user_agent = user_agent
        self.rate_limiter = rate_limiter or RateLimiter(max_per_second)
        self._client = httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SecClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def get(self, url: str) -> httpx.Response:
        """GET with rate limiting and exponential backoff on 403/429."""
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            self.rate_limiter.acquire()
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                last_exc = exc
                delay = BASE_BACKOFF_SECONDS * (2**attempt)
                logger.warning(
                    "SEC request error url=%s attempt=%s error=%s; backing off %.1fs",
                    url,
                    attempt + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue

            if response.status_code in (403, 429):
                delay = BASE_BACKOFF_SECONDS * (2**attempt)
                logger.warning(
                    "SEC rate/forbidden status=%s url=%s attempt=%s; backing off %.1fs",
                    response.status_code,
                    url,
                    attempt + 1,
                    delay,
                )
                time.sleep(delay)
                continue

            if response.status_code >= 500:
                delay = BASE_BACKOFF_SECONDS * (2**attempt)
                logger.warning(
                    "SEC server error status=%s url=%s attempt=%s; backing off %.1fs",
                    response.status_code,
                    url,
                    attempt + 1,
                    delay,
                )
                time.sleep(delay)
                continue

            response.raise_for_status()
            return response

        if last_exc is not None:
            raise last_exc
        raise httpx.HTTPStatusError(
            f"SEC request failed after {MAX_RETRIES} attempts: {url}",
            request=httpx.Request("GET", url),
            response=response,  # type: ignore[possibly-undefined]
        )
