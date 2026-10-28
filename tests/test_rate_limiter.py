"""Tests for the SEC request rate limiter."""

from __future__ import annotations

import time

import pytest

from backend.sec.rate_limiter import RateLimiter


def test_rate_limiter_allows_burst_under_cap():
    limiter = RateLimiter(max_per_second=8)
    start = time.monotonic()
    for _ in range(8):
        waited = limiter.acquire()
        assert waited == 0.0
    elapsed = time.monotonic() - start
    assert elapsed < 0.5


def test_rate_limiter_blocks_ninth_request():
    limiter = RateLimiter(max_per_second=5)
    for _ in range(5):
        limiter.acquire()

    start = time.monotonic()
    waited = limiter.acquire()
    elapsed = time.monotonic() - start

    assert waited > 0.0
    assert elapsed >= 0.15  # some delay within the 1s window


def test_rate_limiter_rejects_non_positive():
    with pytest.raises(ValueError):
        RateLimiter(max_per_second=0)
    with pytest.raises(ValueError):
        RateLimiter(max_per_second=-1)


@pytest.mark.asyncio
async def test_rate_limiter_async_acquire():
    limiter = RateLimiter(max_per_second=3)
    for _ in range(3):
        waited = await limiter.acquire_async()
        assert waited == 0.0

    start = time.monotonic()
    waited = await limiter.acquire_async()
    elapsed = time.monotonic() - start
    assert waited > 0.0
    assert elapsed >= 0.15


def test_rate_limiter_reset():
    limiter = RateLimiter(max_per_second=2)
    limiter.acquire()
    limiter.acquire()
    limiter.reset()
    assert limiter.acquire() == 0.0
