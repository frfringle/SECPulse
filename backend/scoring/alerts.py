"""Persist alerts and durable scoring-queue rows."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from backend.models import Alert, Filing, ScoringQueueItem
from backend.scoring.schema import ScoringResult


def create_alert(
    session: Session,
    *,
    filing: Filing,
    result: ScoringResult,
    source: str,
) -> Alert:
    alert = Alert(
        filing_id=filing.id,  # type: ignore[arg-type]
        accession_number=filing.accession_number,
        ticker=filing.ticker,
        form_type=filing.form_type,
        company_name=filing.company_name,
        direction=result.direction,
        confidence=result.confidence,
        summary=result.summary,
        key_evidence=result.key_evidence,
        event_type=result.event_type,
        source=source,
    )
    session.add(alert)
    return alert


def enqueue_scoring_retry(
    session: Session,
    *,
    filing: Filing,
    filing_text: str,
    priority: int,
    error: str,
) -> ScoringQueueItem:
    """Insert or refresh a pending scoring queue row — never drop the filing."""
    existing = session.exec(
        select(ScoringQueueItem).where(
            ScoringQueueItem.filing_id == filing.id,
            ScoringQueueItem.status == "pending",
        )
    ).first()
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.filing_text = filing_text
        existing.priority = priority
        existing.attempts += 1
        existing.last_error = error[:512]
        existing.updated_at = now
        session.add(existing)
        filing.score_status = "awaiting_ollama"
        filing.score_attempts = existing.attempts
        filing.last_score_error = error[:512]
        session.add(filing)
        return existing

    item = ScoringQueueItem(
        filing_id=filing.id,  # type: ignore[arg-type]
        accession_number=filing.accession_number,
        form_type=filing.form_type,
        ticker=filing.ticker,
        company_name=filing.company_name,
        filing_text=filing_text,
        priority=priority,
        attempts=1,
        last_error=error[:512],
        status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    filing.score_status = "awaiting_ollama"
    filing.score_attempts = 1
    filing.last_score_error = error[:512]
    session.add(filing)
    return item


def list_pending_scoring(session: Session, limit: int = 50) -> list[ScoringQueueItem]:
    rows = session.exec(
        select(ScoringQueueItem)
        .where(ScoringQueueItem.status == "pending")
        .order_by(
            ScoringQueueItem.priority.desc(),  # type: ignore[attr-defined]
            ScoringQueueItem.id,
        )
        .limit(limit)
    ).all()
    return list(rows)


def mark_queue_done(session: Session, item: ScoringQueueItem) -> None:
    item.status = "done"
    item.updated_at = datetime.now(timezone.utc)
    session.add(item)
