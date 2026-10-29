"""Persist alerts and durable scoring-queue rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from backend.api.serialize import alert_to_dict
from backend.api.sse import alert_bus
from backend.models import Alert, EightKExtraction, Filing, ScoringQueueItem
from backend.prices.enrichment import enrich_alert_fields
from backend.prices.yfinance_client import YFinanceClient
from backend.scoring.schema import ScoringResult

_yf_client: Optional[YFinanceClient] = None


def get_yf_client() -> YFinanceClient:
    global _yf_client
    if _yf_client is None:
        _yf_client = YFinanceClient()
    return _yf_client


def set_yf_client(client: Optional[YFinanceClient]) -> None:
    """Test hook to inject a mocked YFinanceClient."""
    global _yf_client
    _yf_client = client


def _lookup_no_press_release(session: Session, filing: Filing) -> Optional[bool]:
    if filing.form_type not in {"8-K", "8-K/A"}:
        return None
    row = session.exec(
        select(EightKExtraction).where(EightKExtraction.filing_id == filing.id)
    ).first()
    if row is None:
        return None
    return bool(row.no_press_release)


def create_alert(
    session: Session,
    *,
    filing: Filing,
    result: ScoringResult,
    source: str,
    yf_client: Optional[YFinanceClient] = None,
) -> Alert:
    no_pr = _lookup_no_press_release(session, filing)
    enrichment = enrich_alert_fields(
        ticker=filing.ticker,
        accepted_at=filing.accepted_at,
        alert_at=datetime.now(timezone.utc),
        no_press_release=no_pr,
        client=yf_client or get_yf_client(),
    )

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
        latency_seconds=enrichment.latency_seconds,
        price_at_alert=enrichment.price_at_alert,
        price_at_accepted=enrichment.price_at_accepted,
        pct_change_since_accepted=enrichment.pct_change_since_accepted,
        market_cap=enrichment.market_cap,
        market_cap_bucket=enrichment.market_cap_bucket,
        no_press_release=enrichment.no_press_release,
        enrichment_error=enrichment.enrichment_error,
    )
    session.add(alert)
    session.flush()  # assign alert.id before SSE broadcast
    try:
        alert_bus.publish(alert_to_dict(alert))
    except Exception:  # noqa: BLE001 — never fail alert persistence on SSE
        pass
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
