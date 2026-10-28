"""Stage 5: yfinance cache, enrichment fields, graceful failures."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import Alert, EightKExtraction, Filing
from backend.prices.enrichment import enrich_alert_fields
from backend.prices.yfinance_client import YFinanceClient, market_cap_bucket
from backend.scoring.alerts import create_alert, set_yf_client
from backend.scoring.schema import ScoringResult


def test_market_cap_bucket():
    assert market_cap_bucket(None) is None
    assert market_cap_bucket(500_000_000) == "small"
    assert market_cap_bucket(1_999_999_999) == "small"
    assert market_cap_bucket(2_000_000_000) == "mid"
    assert market_cap_bucket(9_999_999_999) == "mid"
    assert market_cap_bucket(10_000_000_000) == "large"


def test_yfinance_cache_ttl():
    calls = {"n": 0}

    def fetcher(ticker: str):
        calls["n"] += 1
        return {"price": 10.0 + calls["n"], "market_cap": 1e9, "currency": "USD"}

    client = YFinanceClient(ttl_seconds=60, fetcher=fetcher, history_fetcher=lambda t, w: 9.0)
    a = client.get_snapshot("AAPL")
    b = client.get_snapshot("AAPL")
    assert calls["n"] == 1
    assert a.price == b.price == 11.0

    # Different ticker is a separate cache entry
    client.get_snapshot("MSFT")
    assert calls["n"] == 2


def test_yfinance_cache_expires():
    calls = {"n": 0}

    def fetcher(ticker: str):
        calls["n"] += 1
        return {"price": float(calls["n"]), "market_cap": 1e9}

    client = YFinanceClient(ttl_seconds=0.05, fetcher=fetcher, history_fetcher=lambda t, w: 1.0)
    client.get_snapshot("X")
    time.sleep(0.06)
    client.get_snapshot("X")
    assert calls["n"] == 2


def test_yfinance_soft_failure():
    def fetcher(ticker: str):
        raise RuntimeError("rate limited")

    client = YFinanceClient(fetcher=fetcher, history_fetcher=lambda t, w: None)
    snap = client.get_snapshot("FAIL")
    assert snap.ok is False
    assert snap.error is not None
    assert "rate limited" in snap.error


def test_enrich_alert_fields_computes_pct_and_latency():
    accepted = datetime.now(timezone.utc) - timedelta(minutes=5)

    def fetcher(ticker: str):
        return {"price": 110.0, "market_cap": 50_000_000_000, "currency": "USD"}

    def history(ticker: str, when: datetime):
        return 100.0

    client = YFinanceClient(fetcher=fetcher, history_fetcher=history)
    enrichment = enrich_alert_fields(
        ticker="AAPL",
        accepted_at=accepted,
        alert_at=datetime.now(timezone.utc),
        no_press_release=True,
        client=client,
    )
    assert enrichment.latency_seconds is not None
    assert enrichment.latency_seconds >= 300
    assert enrichment.price_at_alert == 110.0
    assert enrichment.price_at_accepted == 100.0
    assert enrichment.pct_change_since_accepted == 10.0
    assert enrichment.market_cap_bucket == "large"
    assert enrichment.no_press_release is True
    assert enrichment.enrichment_error is None


def test_enrich_graceful_when_prices_missing():
    def fetcher(ticker: str):
        raise RuntimeError("yahoo down")

    client = YFinanceClient(fetcher=fetcher, history_fetcher=lambda t, w: None)
    enrichment = enrich_alert_fields(
        ticker="ZZZ",
        accepted_at=datetime.now(timezone.utc),
        client=client,
    )
    assert enrichment.price_at_alert is None
    assert enrichment.pct_change_since_accepted is None
    assert enrichment.enrichment_error is not None


def test_create_alert_persists_enrichment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "SECPulse Test test@example.com")

    def fetcher(ticker: str):
        return {"price": 200.0, "market_cap": 3_000_000_000}

    def history(ticker: str, when: datetime):
        return 180.0

    set_yf_client(YFinanceClient(fetcher=fetcher, history_fetcher=history))

    engine = create_engine(
        f"sqlite:///{tmp_path / 'p.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    accepted = datetime.now(timezone.utc) - timedelta(seconds=90)
    with Session(engine) as session:
        filing = Filing(
            accession_number="0000320193-26-000001",
            form_type="8-K",
            cik="0000320193",
            company_name="Apple Inc.",
            ticker="AAPL",
            accepted_at=accepted,
            filing_url="https://www.sec.gov/x-index.htm",
        )
        session.add(filing)
        session.commit()
        session.refresh(filing)
        session.add(
            EightKExtraction(
                filing_id=filing.id,
                accession_number=filing.accession_number,
                ticker="AAPL",
                item_numbers="1.01",
                high_priority_items="1.01",
                has_exhibit_99_1=False,
                no_press_release=True,
                items_json="[]",
                combined_text="Item 1.01",
            )
        )
        session.commit()

        result = ScoringResult(
            direction="bullish",
            confidence=80,
            summary="Material agreement.",
            key_evidence="Credit Agreement",
            event_type="material_agreement",
        )
        create_alert(session, filing=filing, result=result, source="ollama")
        session.commit()

        alert = session.exec(select(Alert)).one()
        assert alert.price_at_alert == 200.0
        assert alert.price_at_accepted == 180.0
        assert alert.pct_change_since_accepted == round((20 / 180) * 100, 4)
        assert alert.market_cap_bucket == "mid"
        assert alert.no_press_release is True
        assert alert.latency_seconds is not None
        assert alert.latency_seconds >= 90
        assert alert.enrichment_error is None
