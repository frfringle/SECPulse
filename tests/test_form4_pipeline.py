"""Form 4 parse wired through the ingestion poller."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import Filing, Form4TransactionRow
from backend.sec.poller import FilingPoller
from backend.sec.ticker_cache import TickerCache


FORM4_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Latest Filings</title>
  <updated>2026-10-28T16:00:00-04:00</updated>
  <entry>
    <title>4 - Tesla, Inc. (0001318605) (Reporting)</title>
    <link rel="alternate" type="text/html"
      href="https://www.sec.gov/Archives/edgar/data/1318605/000131860526000010/0001318605-26-000010-index.htm"/>
    <id>urn:tag:sec.gov,2008:accession-number=0001318605-26-000010</id>
    <updated>2026-10-28T15:50:00-04:00</updated>
    <summary>Acc-no: 0001318605-26-000010</summary>
  </entry>
</feed>
"""


def test_poller_parses_form4_and_flags_alert(
    fixtures_dir: Path,
    company_tickers_payload: dict,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("SEC_USER_AGENT", "SECPulse Test test@example.com")
    from backend.config import Settings

    settings = Settings()  # type: ignore[call-arg]

    form4_xml = (fixtures_dir / "form4_officer_open_market_buy.xml").read_text()
    index_html = (fixtures_dir / "form4_index.htm").read_text()

    def fake_get(url: str):
        resp = MagicMock()
        if "output=atom" in url or "getcurrent" in url:
            resp.text = FORM4_ATOM
        elif url.endswith("-index.htm"):
            resp.text = index_html
        elif url.endswith(".xml"):
            resp.text = form4_xml
        else:
            raise AssertionError(f"Unexpected URL: {url}")
        return resp

    client = MagicMock()
    client.get.side_effect = fake_get

    cache_file = tmp_path / "tickers.json"
    cache_file.write_text(json.dumps(company_tickers_payload), encoding="utf-8")
    ticker_cache = TickerCache(client=MagicMock(), cache_path=cache_file)
    ticker_cache.load()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def session_factory() -> Session:
        return Session(engine)

    poller = FilingPoller(
        settings=settings,
        client=client,
        ticker_cache=ticker_cache,
        session_factory=session_factory,
    )

    assert poller.poll_once() == 1

    with Session(engine) as session:
        filing = session.exec(select(Filing)).one()
        assert filing.form_type == "4"
        assert filing.form4_parsed is True
        assert filing.ticker == "TSLA"

        rows = list(session.exec(select(Form4TransactionRow)))
        assert len(rows) == 1
        row = rows[0]
        assert row.insider_name == "Jane Officer"
        assert row.transaction_code == "P"
        assert row.shares == 1000
        assert row.price == 250.50
        assert row.total_value == 250500.0
        assert row.alert_by_rule is True
