"""Stage 6 API tests (TestClient; mocked yfinance / no background poller)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.state import app_state
from backend.db import init_db
from backend.models import Alert, Filing
from backend.prices.yfinance_client import YFinanceClient
from backend.scoring.alerts import set_yf_client
from backend.sec.priority import PriorityQueue


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "SECPulse Test test@example.com")
    monkeypatch.setenv("SECPULSE_DISABLE_BACKGROUND", "1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")

    # Clear cached settings from prior tests
    from backend.config import get_settings

    get_settings.cache_clear()

    def fetcher(ticker: str):
        return {"price": 150.0, "market_cap": 8_000_000_000, "currency": "USD"}

    def history(ticker: str, when: datetime):
        return 140.0

    def series(ticker: str, period: str, interval: str):
        return [
            {
                "t": "2026-10-28T15:00:00+00:00",
                "open": 149.0,
                "high": 151.0,
                "low": 148.0,
                "close": 150.0,
                "volume": 1000,
            }
        ]

    set_yf_client(
        YFinanceClient(
            fetcher=fetcher, history_fetcher=history, series_fetcher=series
        )
    )

    app_state.start_background = False
    from backend.config import Settings

    app_state.settings = Settings()  # type: ignore[call-arg]

    from backend.main import create_app

    application = create_app(start_background=False)
    init_db(f"sqlite:///{tmp_path / 'api.db'}")

    with TestClient(application) as client:
        # Lifespan may clear state — re-apply test doubles after startup
        app_state.processor = type("P", (), {"queue": PriorityQueue()})()
        app_state.last_poll_at = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
        app_state.last_poll_inserted = 2
        app_state.last_poll_error = None
        app_state.ollama_client = type(
            "O", (), {"is_available": lambda self: True}
        )()
        app_state.settings = Settings()  # type: ignore[call-arg]

        from backend.db import session_scope

        with session_scope() as session:
            filing = Filing(
                accession_number="0000320193-26-000001",
                form_type="8-K",
                cik="0000320193",
                company_name="Apple Inc.",
                ticker="AAPL",
                accepted_at=datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc),
                filing_url="https://www.sec.gov/x-index.htm",
            )
            session.add(filing)
            session.commit()
            session.refresh(filing)
            session.add(
                Alert(
                    filing_id=filing.id,
                    accession_number=filing.accession_number,
                    ticker="AAPL",
                    form_type="8-K",
                    company_name="Apple Inc.",
                    direction="bullish",
                    confidence=80,
                    summary="Material deal.",
                    key_evidence="Item 1.01",
                    event_type="material_agreement",
                    source="ollama",
                    market_cap_bucket="mid",
                    no_press_release=False,
                    price_at_alert=150.0,
                    latency_seconds=120.0,
                )
            )
            session.add(
                Alert(
                    filing_id=filing.id,
                    accession_number="0000320193-26-000002",
                    ticker="AAPL",
                    form_type="4",
                    company_name="Apple Inc.",
                    direction="bullish",
                    confidence=100,
                    summary="Insider buy.",
                    key_evidence="code P",
                    event_type="form4_open_market_buy",
                    source="form4_rule",
                    market_cap_bucket="large",
                    price_at_alert=151.0,
                )
            )
            session.add(
                Alert(
                    filing_id=filing.id,
                    accession_number="0000789019-26-000004",
                    ticker="MSFT",
                    form_type="8-K",
                    company_name="Microsoft Corp",
                    direction="bearish",
                    confidence=70,
                    summary="Auditor change.",
                    key_evidence="Item 4.01",
                    event_type="auditor_change",
                    source="ollama",
                    market_cap_bucket="large",
                )
            )
            session.commit()

        yield client

    get_settings.cache_clear()
    app_state.processor = None
    app_state.ollama_client = None


def test_health(api_client: TestClient):
    resp = api_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["stage"] == 6
    assert data["queue_size"] == 0
    assert data["ollama_reachable"] is True
    assert data["last_poll_at"] is not None
    assert data["last_poll_inserted"] == 2


def test_list_alerts_filters(api_client: TestClient):
    all_resp = api_client.get("/api/alerts")
    assert all_resp.status_code == 200
    assert all_resp.json()["count"] == 3

    aapl = api_client.get("/api/alerts", params={"ticker": "AAPL"})
    assert aapl.json()["count"] == 2

    bear = api_client.get("/api/alerts", params={"direction": "bearish"})
    assert bear.json()["count"] == 1
    assert bear.json()["alerts"][0]["ticker"] == "MSFT"

    form4 = api_client.get("/api/alerts", params={"form_type": "4"})
    assert form4.json()["count"] == 1

    conf = api_client.get("/api/alerts", params={"min_confidence": 90})
    assert conf.json()["count"] == 1
    assert conf.json()["alerts"][0]["confidence"] == 100

    mid = api_client.get("/api/alerts", params={"market_cap_bucket": "mid"})
    assert mid.json()["count"] == 1
    assert mid.json()["alerts"][0]["ticker"] == "AAPL"


def test_get_alert_by_id(api_client: TestClient):
    listing = api_client.get("/api/alerts", params={"ticker": "MSFT"}).json()
    alert_id = listing["alerts"][0]["id"]
    resp = api_client.get(f"/api/alerts/{alert_id}")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "MSFT"
    assert resp.json()["direction"] == "bearish"

    missing = api_client.get("/api/alerts/999999")
    assert missing.status_code == 404


def test_ticker_detail(api_client: TestClient):
    resp = api_client.get("/api/tickers/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAPL"
    assert data["price"] == 150.0
    assert data["market_cap_bucket"] == "mid"
    assert data["alert_count"] == 2
    assert data["history"]["intraday"]
    assert data["history"]["five_day"]
    assert data["history"]["intraday"][0]["close"] == 150.0


def test_sse_stream_connects(api_client: TestClient):
    with api_client.stream("GET", "/api/stream") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        # Read first chunk (connected comment)
        chunk = next(resp.iter_bytes())
        assert b"connected" in chunk or b":" in chunk


def test_sse_broadcast_on_create_alert(api_client: TestClient):
    from backend.api.sse import alert_bus
    from backend.db import session_scope
    from backend.scoring.alerts import create_alert
    from backend.scoring.schema import ScoringResult

    published: list[dict] = []
    original = alert_bus.publish

    def capture(payload):
        published.append(payload)
        return original(payload)

    alert_bus.publish = capture  # type: ignore[method-assign]
    try:
        with session_scope() as session:
            filing = session.get(Filing, 1)
            assert filing is not None
            create_alert(
                session,
                filing=filing,
                result=ScoringResult(
                    direction="bullish",
                    confidence=90,
                    summary="New alert for SSE.",
                    key_evidence="evidence",
                    event_type="test_event",
                ),
                source="ollama",
            )
            session.commit()
        assert published
        assert published[0]["event_type"] == "test_event"
        assert published[0]["ticker"] == "AAPL"
        assert published[0]["id"] is not None
    finally:
        alert_bus.publish = original  # type: ignore[method-assign]
