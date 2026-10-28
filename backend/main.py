"""SECPulse FastAPI application — Stage 6: API."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from backend.api.routes import router as api_router
from backend.api.state import app_state
from backend.config import require_settings
from backend.db import init_db, session_scope
from backend.logging_config import configure_logging
from backend.scoring.ollama import OllamaClient
from backend.sec.client import SecClient
from backend.sec.poller import FilingPoller
from backend.sec.processor import FilingProcessor
from backend.sec.rate_limiter import RateLimiter
from backend.sec.ticker_cache import TickerCache

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_client: SecClient | None = None
_ollama: OllamaClient | None = None


def _should_start_background() -> bool:
    if not app_state.start_background:
        return False
    return os.environ.get("SECPULSE_DISABLE_BACKGROUND", "").lower() not in {
        "1",
        "true",
        "yes",
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler, _client, _ollama

    settings = require_settings()
    configure_logging(settings.log_level)
    init_db(settings.database_url)
    app_state.settings = settings
    app_state.stage = 6

    if _should_start_background():
        _ollama = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
        app_state.ollama_client = _ollama

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

        processor = FilingProcessor(
            settings=settings,
            client=_client,
            session_factory=session_scope,
            ollama_client=_ollama,
        )
        poller = FilingPoller(
            settings=settings,
            client=_client,
            ticker_cache=ticker_cache,
            session_factory=session_scope,
            processor=processor,
        )
        app_state.processor = processor
        app_state.poller = poller

        _scheduler = BackgroundScheduler()
        _scheduler.add_job(
            poller.poll_once,
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
        try:
            poller.poll_once()
        except Exception as exc:  # noqa: BLE001
            logger.error("Initial poll failed (continuing): %s", exc)
    else:
        logger.info("Background poller disabled (test / SECPULSE_DISABLE_BACKGROUND)")

    yield

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _client is not None:
        _client.close()
        _client = None
    if _ollama is not None:
        _ollama.close()
        _ollama = None
    app_state.processor = None
    app_state.poller = None
    app_state.ollama_client = None
    logger.info("SECPulse shutdown complete")


def create_app(*, start_background: bool | None = None) -> FastAPI:
    """App factory — set start_background=False for TestClient."""
    if start_background is not None:
        app_state.start_background = start_background
    application = FastAPI(
        title="SECPulse",
        version="0.1.0",
        description="Personal SEC EDGAR alert dashboard (Stage 6: API)",
        lifespan=lifespan,
    )
    application.include_router(api_router)
    return application


app = create_app()


def run() -> None:
    """Entrypoint used by `python -m backend.main` / uvicorn."""
    import uvicorn

    require_settings()
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()
