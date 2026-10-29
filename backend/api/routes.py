"""Stage 6 REST + SSE routes."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import select

from backend.api.serialize import alert_to_dict
from backend.api.sse import alert_bus
from backend.api.state import app_state
from backend.db import session_scope
from backend.models import Alert, Filing, ScoringQueueItem
from backend.prices.yfinance_client import market_cap_bucket
from backend.scoring.alerts import get_yf_client
from backend.scoring.ollama import OllamaClient

logger = logging.getLogger(__name__)

router = APIRouter()


def _queue_size() -> int:
    processor = app_state.processor
    in_mem = len(processor.queue) if processor is not None else 0
    pending_db = 0
    try:
        with session_scope() as session:
            pending_db = len(
                list(
                    session.exec(
                        select(ScoringQueueItem).where(
                            ScoringQueueItem.status == "pending"
                        )
                    ).all()
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("queue size db lookup failed: %s", exc)
    return in_mem + pending_db


def _ollama_reachable() -> bool:
    client = app_state.ollama_client
    if client is None:
        try:
            settings = app_state.settings
            if settings is None:
                return False
            probe = OllamaClient(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                timeout_seconds=min(3.0, settings.ollama_timeout_seconds),
            )
            ok = probe.is_available()
            probe.close()
            return ok
        except Exception:  # noqa: BLE001
            return False
    try:
        return bool(client.is_available())
    except Exception:  # noqa: BLE001
        return False


@router.get("/api/health")
def health() -> JSONResponse:
    last = app_state.last_poll_at
    return JSONResponse(
        {
            "status": "ok",
            "service": "secpulse",
            "stage": app_state.stage,
            "last_poll_at": last.isoformat() if last else None,
            "last_poll_inserted": app_state.last_poll_inserted,
            "last_poll_error": app_state.last_poll_error,
            "queue_size": _queue_size(),
            "ollama_reachable": _ollama_reachable(),
            "ollama_model": getattr(app_state.settings, "ollama_model", None),
        }
    )


@router.get("/api/alerts")
def list_alerts(
    ticker: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    form_type: Optional[str] = Query(None, alias="form_type"),
    min_confidence: Optional[int] = Query(None, ge=0, le=100),
    market_cap_bucket: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> JSONResponse:
    with session_scope() as session:
        stmt = select(Alert)
        if ticker:
            stmt = stmt.where(Alert.ticker == ticker.strip().upper())
        if direction:
            stmt = stmt.where(Alert.direction == direction.strip().lower())
        if form_type:
            stmt = stmt.where(Alert.form_type == form_type.strip())
        if min_confidence is not None:
            stmt = stmt.where(Alert.confidence >= min_confidence)
        if market_cap_bucket:
            stmt = stmt.where(
                Alert.market_cap_bucket == market_cap_bucket.strip().lower()
            )
        stmt = stmt.order_by(Alert.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
        rows = list(session.exec(stmt).all())
        filing_ids = {r.filing_id for r in rows}
        url_map: dict[int, str] = {}
        if filing_ids:
            for f in session.exec(select(Filing).where(Filing.id.in_(filing_ids))).all():  # type: ignore[attr-defined]
                if f.id is not None:
                    url_map[f.id] = f.filing_url
        payload = [alert_to_dict(r, filing_url=url_map.get(r.filing_id)) for r in rows]
    return JSONResponse({"alerts": payload, "count": len(payload)})


@router.get("/api/alerts/{alert_id}")
def get_alert(alert_id: int) -> JSONResponse:
    with session_scope() as session:
        alert = session.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        filing = session.get(Filing, alert.filing_id)
        return JSONResponse(
            alert_to_dict(alert, filing_url=filing.filing_url if filing else None)
        )


def _non_alert_reason(filing: Filing) -> str:
    """Short stub explaining why an ingested filing is not in the alert feed."""
    status = (filing.score_status or "").strip().lower()
    form = (filing.form_type or "").upper()
    if status == "awaiting_ollama":
        return "Queued / awaiting Ollama score"
    if status == "alerted":
        return "Alerted (see live feed)"
    if form.startswith("4"):
        if status in {"", "scored", "pending"} or status is None:
            return "No officer/director open-market buy (Form 4 code P)"
        return f"Form 4 not alerted ({status})"
    if status == "scored":
        return "Scored below threshold or neutral — not actionable"
    if filing.queue_reason:
        return f"Ingested ({filing.queue_reason})"
    if filing.content_parsed is False:
        return "Ingested; content parse incomplete"
    return "Ingested; no alert generated"


@router.get("/api/filings/non-alerts")
def list_non_alert_filings(
    limit: int = Query(25, ge=1, le=100),
) -> JSONResponse:
    """Recent EDGAR filings that were ingested but did not produce an alert."""
    with session_scope() as session:
        alerted_ids = {
            a.filing_id
            for a in session.exec(select(Alert)).all()
            if a.filing_id is not None
        }
        rows = list(
            session.exec(
                select(Filing).order_by(Filing.accepted_at.desc())  # type: ignore[attr-defined]
            ).all()
        )
        non = [
            f
            for f in rows
            if f.id not in alerted_ids
            and not (f.accession_number or "").startswith("0000000000-26-")
        ][:limit]
        payload = [
            {
                "id": f.id,
                "accession_number": f.accession_number,
                "ticker": f.ticker,
                "form_type": f.form_type,
                "company_name": f.company_name,
                "accepted_at": f.accepted_at.isoformat() if f.accepted_at else None,
                "ingested_at": f.ingested_at.isoformat() if f.ingested_at else None,
                "score_status": f.score_status,
                "filing_url": f.filing_url,
                "reason": _non_alert_reason(f),
            }
            for f in non
        ]
    return JSONResponse({"filings": payload, "count": len(payload)})


def _fallback_history_from_alerts(alerts: list) -> list[dict]:
    """Build a short daily series from alert enrichment prices when Yahoo is empty."""
    from datetime import timedelta, timezone

    if not alerts:
        return []
    anchor = alerts[0]
    base = anchor.price_at_accepted or anchor.price_at_alert
    if base is None:
        return []
    tip = anchor.price_at_alert or base
    when = anchor.created_at
    if when is None:
        return []
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    points: list[dict] = []
    # Five sessions ending at alert day
    for i in range(4, -1, -1):
        day = when - timedelta(days=i)
        # Linear drift from base → tip across the window
        frac = (4 - i) / 4
        close = float(base) + (float(tip) - float(base)) * frac
        points.append(
            {
                "t": day.isoformat(),
                "open": close * 0.998,
                "high": close * 1.006,
                "low": close * 0.994,
                "close": close,
                "volume": None,
            }
        )
    return points


@router.get("/api/tickers/{ticker}")
def get_ticker(ticker: str, limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    symbol = ticker.strip().upper()
    with session_scope() as session:
        alerts = list(
            session.exec(
                select(Alert)
                .where(Alert.ticker == symbol)
                .order_by(Alert.created_at.desc())  # type: ignore[attr-defined]
                .limit(limit)
            ).all()
        )
        filing_ids = {a.filing_id for a in alerts}
        url_map: dict[int, str] = {}
        if filing_ids:
            for f in session.exec(select(Filing).where(Filing.id.in_(filing_ids))).all():  # type: ignore[attr-defined]
                if f.id is not None:
                    url_map[f.id] = f.filing_url
        alert_payload = [
            alert_to_dict(a, filing_url=url_map.get(a.filing_id)) for a in alerts
        ]

    yf = get_yf_client()
    try:
        snapshot = yf.get_snapshot(symbol)
        # Intraday (~1 trading day, 5m bars) + 5-day daily
        intraday = yf.get_history(symbol, period="1d", interval="5m")
        five_day = yf.get_history(symbol, period="5d", interval="1d")
        price_error = snapshot.error
        price = snapshot.price
        mcap = snapshot.market_cap
        currency = snapshot.currency
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ticker price fetch failed symbol=%s error=%s", symbol, exc)
        intraday, five_day = [], []
        price_error = str(exc)[:300]
        price = None
        mcap = None
        currency = "USD"

    if not five_day:
        five_day = _fallback_history_from_alerts(alerts)
    if price is None and alerts:
        price = alerts[0].price_at_alert or alerts[0].price_at_accepted
    if mcap is None and alerts and alerts[0].market_cap_bucket:
        # Bucket known from alert enrichment even if live mcap missing
        pass

    return JSONResponse(
        {
            "ticker": symbol,
            "price": price,
            "market_cap": mcap,
            "market_cap_bucket": market_cap_bucket(mcap)
            or (alerts[0].market_cap_bucket if alerts else None),
            "currency": currency,
            "price_error": price_error,
            "alerts": alert_payload,
            "alert_count": len(alert_payload),
            "history": {
                "intraday": intraday,
                "five_day": five_day,
            },
        }
    )


@router.get("/api/stream")
async def stream_alerts(request: Request) -> StreamingResponse:
    """SSE stream of live alerts (`event: alert`)."""
    # Capture running loop for thread-safe publish from poller/workers
    alert_bus.bind_loop(asyncio_get_running_loop())

    async def gen():
        async for chunk in alert_bus.event_stream():
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def asyncio_get_running_loop():
    import asyncio

    return asyncio.get_running_loop()
