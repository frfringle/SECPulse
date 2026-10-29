"""SECPulse FastAPI application — Stage 7: API + React UI."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router as api_router
from backend.api.state import app_state
from backend.config import PROJECT_ROOT, require_settings
from backend.db import init_db, session_scope
from backend.logging_config import configure_logging
from backend.scoring.ollama import OllamaClient
from backend.patents.assignee_map import AssigneeMap
from backend.patents.client import UsptoClient
from backend.patents.poller import PatentPoller
from backend.sec.client import SecClient
from backend.sec.poller import FilingPoller
from backend.sec.processor import FilingProcessor
from backend.sec.rate_limiter import RateLimiter
from backend.sec.ticker_cache import TickerCache

logger = logging.getLogger(__name__)

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

_scheduler: BackgroundScheduler | None = None
_client: SecClient | None = None
_ollama: OllamaClient | None = None
_uspto: UsptoClient | None = None


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
    global _scheduler, _client, _ollama, _uspto

    settings = require_settings()
    configure_logging(settings.log_level)
    # Ensure PatentEvent metadata is registered before create_all
    import backend.models  # noqa: F401

    init_db(settings.database_url)
    app_state.settings = settings
    app_state.stage = 7

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

        # Patent watch — optional; EDGAR keeps running without USPTO_API_KEY
        if settings.uspto_api_key:
            try:
                assignee_map = AssigneeMap(settings.assignee_alias_path)
                assignee_map.load()
                uspto_limiter = RateLimiter(settings.uspto_max_requests_per_second)
                _uspto = UsptoClient(
                    settings.uspto_api_key,
                    rate_limiter=uspto_limiter,
                    max_per_second=settings.uspto_max_requests_per_second,
                )
                patent_poller = PatentPoller(
                    client=_uspto,
                    assignee_map=assignee_map,
                    session_factory=session_scope,
                )
                app_state.patent_poller = patent_poller
                _scheduler.add_job(
                    patent_poller.poll_once,
                    trigger="interval",
                    seconds=settings.uspto_poll_interval_seconds,
                    id="uspto_patent_poll",
                    max_instances=1,
                    coalesce=True,
                )
                logger.info(
                    "USPTO patent poller enabled interval=%ss",
                    settings.uspto_poll_interval_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("USPTO patent poller setup failed (EDGAR continues): %s", exc)
        else:
            logger.info(
                "USPTO_API_KEY unset — patent poller disabled (EDGAR only). "
                "Add USPTO_API_KEY from https://data.uspto.gov/apis to enable."
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
        if app_state.patent_poller is not None:
            try:
                app_state.patent_poller.poll_once()
            except Exception as exc:  # noqa: BLE001
                logger.error("Initial USPTO poll failed (continuing): %s", exc)
    else:
        logger.info("Background poller disabled (test / SECPULSE_DISABLE_BACKGROUND)")

    yield

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _client is not None:
        _client.close()
        _client = None
    if _uspto is not None:
        _uspto.close()
        _uspto = None
    if _ollama is not None:
        _ollama.close()
        _ollama = None
    app_state.processor = None
    app_state.poller = None
    app_state.patent_poller = None
    app_state.ollama_client = None
    logger.info("SECPulse shutdown complete")


def _mount_frontend(application: FastAPI) -> None:
    """Serve the Vite build when present (production / make run)."""
    if not FRONTEND_DIST.is_dir():
        logger.warning(
            "frontend/dist missing — run `cd frontend && npm run build` "
            "or use `make dev` with Vite proxy"
        )
        return

    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=str(assets)),
            name="assets",
        )

    @application.get("/favicon.svg", include_in_schema=False)
    def favicon():
        path = FRONTEND_DIST / "favicon.svg"
        if path.is_file():
            return FileResponse(path)
        return FileResponse(PROJECT_ROOT / "frontend" / "public" / "favicon.svg")

    @application.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Never swallow API routes (mounted earlier)
        if full_path.startswith("api/") or full_path == "api":
            return {"detail": "Not Found"}
        index = FRONTEND_DIST / "index.html"
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file() and FRONTEND_DIST in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(index)


def create_app(*, start_background: bool | None = None) -> FastAPI:
    """App factory — set start_background=False for TestClient."""
    if start_background is not None:
        app_state.start_background = start_background
    application = FastAPI(
        title="SECPulse",
        version="0.1.0",
        description="Personal SEC EDGAR alert dashboard (Stage 7: frontend)",
        lifespan=lifespan,
    )
    # Optional: allow a Netlify (or other) static UI to call this API cross-origin.
    # CORS_ORIGINS="https://your-site.netlify.app,http://localhost:5173"
    cors_origins = [
        o.strip()
        for o in os.environ.get("CORS_ORIGINS", "").split(",")
        if o.strip()
    ]
    if cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    application.include_router(api_router)
    if os.environ.get("SECPULSE_SKIP_FRONTEND", "").lower() not in {
        "1",
        "true",
        "yes",
    }:
        _mount_frontend(application)
    return application


app = create_app()


def run() -> None:
    """Entrypoint used by `python -m backend.main` / uvicorn.

    Honors ``PORT`` (Railway/Render/Fly) and falls back to 8000 locally.
    """
    import uvicorn

    require_settings()
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    run()
