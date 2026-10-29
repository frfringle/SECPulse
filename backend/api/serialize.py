"""Alert / filing JSON serializers."""

from __future__ import annotations

from typing import Any, Optional

from backend.models import Alert, PatentEvent


def alert_to_dict(alert: Alert, *, filing_url: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": alert.id,
        "filing_id": alert.filing_id,
        "accession_number": alert.accession_number,
        "ticker": alert.ticker,
        "form_type": alert.form_type,
        "company_name": alert.company_name,
        "direction": alert.direction,
        "confidence": alert.confidence,
        "summary": alert.summary,
        "key_evidence": alert.key_evidence,
        "event_type": alert.event_type,
        "source": alert.source,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "latency_seconds": alert.latency_seconds,
        "price_at_alert": alert.price_at_alert,
        "price_at_accepted": alert.price_at_accepted,
        "pct_change_since_accepted": alert.pct_change_since_accepted,
        "market_cap": alert.market_cap,
        "market_cap_bucket": alert.market_cap_bucket,
        "no_press_release": alert.no_press_release,
        "enrichment_error": alert.enrichment_error,
        "filing_url": filing_url,
    }


def patent_to_dict(event: PatentEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "application_number": event.application_number,
        "patent_number": event.patent_number,
        "event_type": event.event_type,
        "title": event.title,
        "assignee": event.assignee,
        "ticker": event.ticker,
        "status_label": event.status_label,
        "event_at": event.event_at.isoformat() if event.event_at else None,
        "uspto_url": event.uspto_url,
        "google_patents_url": event.google_patents_url,
        "actionable": event.actionable,
        "reason": event.reason,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "source": "uspto",
    }
