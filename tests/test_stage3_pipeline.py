"""Integration: processor extracts 8-K / SC 13D via mocked EDGAR docs."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import EightKExtraction, Filing, SC13DExtraction
from backend.sec.priority import JobPriority
from backend.sec.processor import FilingProcessor


def _engine(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 's3.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_processor_eightk_and_priority(
    fixtures_dir: Path, tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("SEC_USER_AGENT", "SECPulse Test test@example.com")
    from backend.config import Settings

    settings = Settings()  # type: ignore[call-arg]
    engine = _engine(tmp_path)

    index = (fixtures_dir / "eightk_index.htm").read_text()
    primary = (fixtures_dir / "eightk_high_priority.htm").read_text()
    exhibit = (fixtures_dir / "eightk_exhibit_99_1.htm").read_text()

    def fake_get(url: str):
        resp = MagicMock()
        if url.endswith("-index.htm"):
            resp.text = index
        elif url.endswith("eightk_exhibit_99_1.htm"):
            resp.text = exhibit
        elif url.endswith("eightk_high_priority.htm"):
            resp.text = primary
        else:
            resp.text = primary
        return resp

    client = MagicMock()
    client.get.side_effect = fake_get

    def session_factory() -> Session:
        return Session(engine)

    with Session(engine) as session:
        filing = Filing(
            accession_number="0000320193-26-000001",
            form_type="8-K",
            cik="0000320193",
            company_name="Apple Inc.",
            ticker="AAPL",
            accepted_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
            filing_url=(
                "https://www.sec.gov/Archives/edgar/data/320193/"
                "000032019326000001/0000320193-26-000001-index.htm"
            ),
        )
        session.add(filing)
        session.commit()
        session.refresh(filing)
        filing_id = filing.id

    processor = FilingProcessor(settings, client, session_factory)
    with Session(engine) as session:
        filing = session.get(Filing, filing_id)
        assert filing is not None
        job = processor.enqueue_filing(filing)
        session.add(filing)
        session.commit()

    # Before extraction we only know form type → eightk_other; after → high
    assert job.priority == JobPriority.EIGHT_K_OTHER
    assert processor.process_available() == 1

    with Session(engine) as session:
        filing = session.get(Filing, filing_id)
        assert filing is not None
        assert filing.content_parsed is True
        assert filing.queue_priority == int(JobPriority.EIGHT_K_HIGH)
        row = session.exec(select(EightKExtraction)).one()
        assert "1.01" in row.high_priority_items
        assert row.has_exhibit_99_1 is True
        assert row.no_press_release is False
        items = json.loads(row.items_json)
        assert any(i["number"] == "2.01" for i in items)
        assert "Exhibit 99.1" in row.combined_text


def test_processor_sc13d(fixtures_dir: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "SECPulse Test test@example.com")
    from backend.config import Settings

    settings = Settings()  # type: ignore[call-arg]
    engine = _engine(tmp_path)
    doc = (fixtures_dir / "sc13d_sample.htm").read_text()

    index_html = """
    <html><body><table>
      <tr><td><a href="sc13d_sample.htm">SC 13D</a></td><td>SC 13D</td></tr>
    </table></body></html>
    """

    def fake_get(url: str):
        resp = MagicMock()
        resp.text = index_html if url.endswith("-index.htm") else doc
        return resp

    client = MagicMock()
    client.get.side_effect = fake_get

    def session_factory() -> Session:
        return Session(engine)

    with Session(engine) as session:
        filing = Filing(
            accession_number="0001067983-26-000003",
            form_type="SC 13D",
            cik="0001067983",
            company_name="Berkshire Hathaway Inc",
            ticker="BRK-B",
            accepted_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
            filing_url=(
                "https://www.sec.gov/Archives/edgar/data/1067983/"
                "000106798326000003/0001067983-26-000003-index.htm"
            ),
        )
        session.add(filing)
        session.commit()
        session.refresh(filing)
        filing_id = filing.id

    processor = FilingProcessor(settings, client, session_factory)
    with Session(engine) as session:
        filing = session.get(Filing, filing_id)
        assert filing is not None
        processor.enqueue_filing(filing)
        session.add(filing)
        session.commit()

    assert processor.process_available() == 1

    with Session(engine) as session:
        row = session.exec(select(SC13DExtraction)).one()
        assert row.filer_name == "Activist Partners LP"
        assert row.stake_percent == 8.4
        assert "investment purposes" in row.item4_text.lower()
        filing = session.get(Filing, filing_id)
        assert filing is not None
        assert filing.content_parsed is True
        assert filing.queue_priority == int(JobPriority.SC13D)
