"""SECPulse FastAPI application — Stage 1: ingestion + health."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.config import require_settings
from backend.db import init_db, session_scope
from backend.logging_config import configure_logging
from backend.sec.client import SecClient
from backend.sec.poller import FilingPoller
from backend.sec.processor import FilingProcessor
from backend.sec.rate_limiter import RateLimiter
from backend.sec.ticker_cache import TickerCache

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_client: SecClient | None = None
_poller: FilingPoller | None = None
_processor: FilingProcessor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler, _client, _poller, _processor

    settings = require_settings()
    configure_logging(settings.log_level)
    init_db(settings.database_url)

    rate_limiter = RateLimiter(settings.sec_max_requests_per_second)
    _client = SecClient(
        user_agent=settings.sec_user_agent,
        rate_limiter=rate_limiter,
        max_per_second=settings.sec_max_requests_per_second,
    )
    ticker_cache = TickerCache(_client, cache_path=settings.ticker_cache_path)
    try:
        ticker_cache.load()
    except Exception as exc:  # noqa: BLE001
        logger.error("Initial ticker cache load failed (continuing): %s", exc)

    _processor = FilingProcessor(
        settings=settings,
        client=_client,
        session_factory=session_scope,
    )
    _poller = FilingPoller(
        settings=settings,
        client=_client,
        ticker_cache=ticker_cache,
        session_factory=session_scope,
        processor=_processor,
    )

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _poller.poll_once,
        trigger="interval",
        seconds=settings.poll_interval_seconds,
        id="edgar_atom_poll",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started poll_interval=%ss",
        settings.poll_interval_seconds,
    )

    # Kick off an immediate poll so we don't wait a full interval on boot
    try:
        _poller.poll_once()
    except Exception as exc:  # noqa: BLE001
        logger.error("Initial poll failed (continuing): %s", exc)

    yield

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _client is not None:
        _client.close()
        _client = None
    logger.info("SECPulse shutdown complete")


app = FastAPI(
    title="SECPulse",
    version="0.1.0",
    description="Personal SEC EDGAR alert dashboard (Stage 5: price enrichment)",
    lifespan=lifespan,
)


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "secpulse",
            "stage": 5,
        }
    )


@app.get("/api/alerts")
def list_alerts() -> JSONResponse:
    """Alert list including Stage 5 price enrichment (full API in Stage 6)."""
    from sqlmodel import select

    from backend.models import Alert

    with session_scope() as session:
        rows = list(session.exec(select(Alert).order_by(Alert.created_at.desc())).all())  # type: ignore[attr-defined]
        payload = [
            {
                "id": r.id,
                "ticker": r.ticker,
                "form_type": r.form_type,
                "direction": r.direction,
                "confidence": r.confidence,
                "summary": r.summary,
                "event_type": r.event_type,
                "source": r.source,
                "accession_number": r.accession_number,
                "latency_seconds": r.latency_seconds,
                "price_at_alert": r.price_at_alert,
                "price_at_accepted": r.price_at_accepted,
                "pct_change_since_accepted": r.pct_change_since_accepted,
                "market_cap_bucket": r.market_cap_bucket,
                "no_press_release": r.no_press_release,
                "enrichment_error": r.enrichment_error,
            }
            for r in rows[:100]
        ]
    return JSONResponse({"alerts": payload, "count": len(payload)})


def run() -> None:
    """Entrypoint used by `python -m backend.main` / uvicorn."""
    import uvicorn

    require_settings()  # fail fast before binding the port
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()
