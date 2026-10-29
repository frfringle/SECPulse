"""Server-Sent Events broadcast bus for live alerts."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AlertEventBus:
    """Fan-out bus: sync publish from worker threads, async subscribe for SSE."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Optional[str]]] = []
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[Optional[str]]:
        q: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Optional[str]]) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, payload: dict[str, Any]) -> None:
        """Thread-safe publish; drops for slow subscribers (full queue)."""
        data = json.dumps(payload, default=str)
        with self._lock:
            subs = list(self._subscribers)
            loop = self._loop
        if not subs:
            return

        def _put(queue: asyncio.Queue[Optional[str]], message: str) -> None:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.debug("SSE subscriber queue full; dropping event")

        if loop is not None and loop.is_running():
            for q in subs:
                loop.call_soon_threadsafe(_put, q, data)
        else:
            for q in subs:
                _put(q, data)

    async def event_stream(self) -> AsyncIterator[str]:
        q = self.subscribe()
        try:
            # Initial comment so clients know the stream is live
            yield ": connected\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if message is None:
                    break
                yield f"event: alert\ndata: {message}\n\n"
        finally:
            self.unsubscribe(q)


alert_bus = AlertEventBus()
