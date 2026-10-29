"""Priority queue for filing processing (Form 4 buys, SC 13D, high-priority 8-K)."""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from enum import IntEnum
from heapq import heappop, heappush
from typing import Any, Optional


# High-priority 8-K item numbers (Stage 3 plan)
HIGH_PRIORITY_8K_ITEMS = frozenset(
    {
        "1.01",
        "1.03",
        "2.01",
        "2.05",
        "2.06",
        "3.01",
        "4.01",
        "4.02",
        "5.02",
    }
)


class JobPriority(IntEnum):
    """Higher value = process sooner."""

    FORM4_OPEN_MARKET_BUY = 100
    SC13D = 90
    EIGHT_K_HIGH = 80
    EIGHT_K_OTHER = 40
    OTHER = 10


@dataclass(order=True)
class _HeapItem:
    # Negated priority so higher JobPriority pops first
    sort_key: tuple[int, int]
    job: Any = field(compare=False)


@dataclass
class ProcessJob:
    """Unit of work for the Stage 3 processing pipeline."""

    filing_id: int
    accession_number: str
    form_type: str
    ticker: str
    filing_url: str
    priority: JobPriority
    reason: str = ""
    # Optional hints from earlier stages
    high_priority_items: tuple[str, ...] = ()
    form4_alert: bool = False


def priority_for_form(
    form_type: str,
    *,
    form4_alert: bool = False,
    eightk_items: Optional[set[str]] = None,
) -> tuple[JobPriority, str]:
    """Decide queue priority before/after extraction."""
    if form_type == "4" and form4_alert:
        return JobPriority.FORM4_OPEN_MARKET_BUY, "form4_open_market_buy"
    if form_type in {"SC 13D", "SC 13D/A"}:
        return JobPriority.SC13D, "sc13d"
    if form_type in {"8-K", "8-K/A"}:
        items = eightk_items or set()
        high = sorted(items & HIGH_PRIORITY_8K_ITEMS)
        if high:
            return JobPriority.EIGHT_K_HIGH, f"eightk_high:{','.join(high)}"
        return JobPriority.EIGHT_K_OTHER, "eightk_other"
    return JobPriority.OTHER, "other"


class PriorityQueue:
    """Thread-safe max-priority queue for ProcessJob."""

    def __init__(self) -> None:
        self._heap: list[_HeapItem] = []
        self._lock = threading.Lock()
        self._seq = itertools.count()

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)

    def push(self, job: ProcessJob) -> None:
        with self._lock:
            seq = next(self._seq)
            heappush(
                self._heap,
                _HeapItem(sort_key=(-int(job.priority), seq), job=job),
            )

    def pop(self) -> Optional[ProcessJob]:
        with self._lock:
            if not self._heap:
                return None
            return heappop(self._heap).job

    def peek_priority(self) -> Optional[JobPriority]:
        with self._lock:
            if not self._heap:
                return None
            return self._heap[0].job.priority

    def drain(self) -> list[ProcessJob]:
        """Pop all jobs in priority order."""
        jobs: list[ProcessJob] = []
        while True:
            job = self.pop()
            if job is None:
                break
            jobs.append(job)
        return jobs
