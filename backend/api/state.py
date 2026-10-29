"""Mutable runtime state for health / SSE / background workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class AppState:
    stage: int = 7
    last_poll_at: Optional[datetime] = None
    last_poll_inserted: int = 0
    last_poll_error: Optional[str] = None
    processor: Any = None
    poller: Any = None
    ollama_client: Any = None
    settings: Any = None
    # Set False in tests to skip APScheduler / initial SEC poll
    start_background: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


app_state = AppState()
