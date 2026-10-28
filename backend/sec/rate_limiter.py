"""Token-bucket style rate limiter for SEC.gov fair-access requests."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque


class RateLimiter:
    """Limit calls to at most `max_per_second` within a rolling 1-second window.

    Thread-safe (sync) and asyncio-friendly (async acquire).
    """

    def __init__(self, max_per_second: float = 8.0) -> None:
        if max_per_second <= 0:
            raise ValueError("max_per_second must be positive")
        self.max_per_second = float(max_per_second)
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - 1.0
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()

    def _wait_seconds(self, now: float) -> float:
        self._prune(now)
        if len(self._timestamps) < self.max_per_second:
            return 0.0
        oldest = self._timestamps[0]
        return max(0.0, (oldest + 1.0) - now)

    def acquire(self) -> float:
        """Block until a slot is available. Returns seconds waited."""
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                delay = self._wait_seconds(now)
                if delay <= 0:
                    self._timestamps.append(now)
                    return waited
            time.sleep(delay)
            waited += delay

    async def acquire_async(self) -> float:
        """Async variant of acquire. Returns seconds waited."""
        waited = 0.0
        while True:
            async with self._async_lock:
                with self._lock:
                    now = time.monotonic()
                    delay = self._wait_seconds(now)
                    if delay <= 0:
                        self._timestamps.append(now)
                        return waited
            await asyncio.sleep(delay)
            waited += delay

    def reset(self) -> None:
        with self._lock:
            self._timestamps.clear()
