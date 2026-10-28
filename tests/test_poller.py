"""Integration-ish tests for poller dedupe and ticker skip."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import Filing
from backend.sec.poller import FilingPoller
from backend.sec.ticker_cache import TickerCache


def _make_session_factory(db_path: Path):
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def factory() -> Session:
        return Session(engine)

    return factory, engine


def test_poller_inserts_dedupes_and_skips_unknown_cik(
    sample_atom_xml: str,
    company_tickers_payload: dict,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("SEC_USER_AGENT", "SECPulse Test test@example.com")
    from backend.config import Settings

    settings = Settings()  # type: ignore[call-arg]

    cache_file = tmp_path / "tickers.json"
    cache_file.write_text(json.dumps(company_tickers_payload), encoding="utf-8")

    response = MagicMock()
    response.text = sample_atom_xml
    client = MagicMock()
    client.get.return_value = response

    ticker_cache = TickerCache(client=MagicMock(), cache_path=cache_file)
    ticker_cache.load()

    session_factory, engine = _make_session_factory(tmp_path / "test.db")
    poller = FilingPoller(
        settings=settings,
        client=client,
        ticker_cache=ticker_cache,
        session_factory=session_factory,
    )

    inserted_first = poller.poll_once()
    inserted_second = poller.poll_once()

    with Session(engine) as session:
        rows = list(session.exec(select(Filing)))
        accessions = {r.accession_number for r in rows}
        tickers = {r.ticker for r in rows}

    # Watched with tickers: AAPL 8-K, TSLA 4, BRK-B SC13D/A, MSFT 8-K/A
    # SC 13D Acme (0009999999) has no ticker → skipped
    assert inserted_first == 4
    assert inserted_second == 0  # dedupe
    assert len(rows) == 4
    assert "0009999999-26-000002" not in accessions
    assert tickers == {"AAPL", "TSLA", "BRK-B", "MSFT"}
