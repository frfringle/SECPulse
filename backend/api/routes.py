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
from backend.models import Alert, ScoringQueueItem
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
        payload = [alert_to_dict(r) for r in rows]
    return JSONResponse({"alerts": payload, "count": len(payload)})


@router.get("/api/alerts/{alert_id}")
def get_alert(alert_id: int) -> JSONResponse:
    with session_scope() as session:
        alert = session.get(Alert, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        return JSONResponse(alert_to_dict(alert))


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
        alert_payload = [alert_to_dict(a) for a in alerts]

    yf = get_yf_client()
    snapshot = yf.get_snapshot(symbol)
    # Intraday (~1 trading day, 5m bars) + 5-day daily
    intraday = yf.get_history(symbol, period="1d", interval="5m")
    five_day = yf.get_history(symbol, period="5d", interval="1d")

    return JSONResponse(
        {
            "ticker": symbol,
            "price": snapshot.price,
            "market_cap": snapshot.market_cap,
            "market_cap_bucket": market_cap_bucket(snapshot.market_cap),
            "currency": snapshot.currency,
            "price_error": snapshot.error,
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
