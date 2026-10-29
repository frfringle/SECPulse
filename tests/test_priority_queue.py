"""Tests for processing priority ordering."""

from __future__ import annotations

from backend.sec.priority import (
    HIGH_PRIORITY_8K_ITEMS,
    JobPriority,
    PriorityQueue,
    ProcessJob,
    priority_for_form,
)


def test_high_priority_item_set():
    assert "1.01" in HIGH_PRIORITY_8K_ITEMS
    assert "5.02" in HIGH_PRIORITY_8K_ITEMS
    assert "2.02" not in HIGH_PRIORITY_8K_ITEMS
    assert "9.01" not in HIGH_PRIORITY_8K_ITEMS


def test_priority_for_form_ordering():
    p4, _ = priority_for_form("4", form4_alert=True)
    p13, _ = priority_for_form("SC 13D")
    p8h, reason = priority_for_form("8-K", eightk_items={"1.01", "9.01"})
    p8o, _ = priority_for_form("8-K", eightk_items={"2.02"})
    assert p4 > p13 > p8h > p8o
    assert "1.01" in reason


def test_priority_queue_pops_highest_first():
    q = PriorityQueue()
    q.push(
        ProcessJob(
            filing_id=1,
            accession_number="a",
            form_type="8-K",
            ticker="X",
            filing_url="u",
            priority=JobPriority.EIGHT_K_OTHER,
        )
    )
    q.push(
        ProcessJob(
            filing_id=2,
            accession_number="b",
            form_type="4",
            ticker="Y",
            filing_url="u",
            priority=JobPriority.FORM4_OPEN_MARKET_BUY,
            form4_alert=True,
        )
    )
    q.push(
        ProcessJob(
            filing_id=3,
            accession_number="c",
            form_type="SC 13D",
            ticker="Z",
            filing_url="u",
            priority=JobPriority.SC13D,
        )
    )
    ordered = [j.accession_number for j in q.drain()]
    assert ordered == ["b", "c", "a"]
