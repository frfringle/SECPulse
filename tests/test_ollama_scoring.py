"""Stage 4: Ollama JSON validation, retry, alert rules (mocked Ollama)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import Alert, Filing, Form4TransactionRow, ScoringQueueItem
from backend.scoring.ollama import OllamaClient, OllamaError
from backend.scoring.schema import ScoringResult, parse_scoring_json
from backend.scoring.scorer import FilingScorer, form4_rule_score
from backend.sec.processor import FilingProcessor


def test_parse_scoring_json_valid():
    raw = json.dumps(
        {
            "direction": "Bullish",
            "confidence": "80",
            "summary": "Material acquisition announced. Likely positive near-term reaction.",
            "key_evidence": "completed the acquisition of Target LLC",
            "event_type": "acquisition",
        }
    )
    result = parse_scoring_json(raw)
    assert result.direction == "bullish"
    assert result.confidence == 80
    assert result.should_alert(65) is True
    assert result.should_alert(90) is False


def test_parse_scoring_json_rejects_bad_direction():
    with pytest.raises((ValidationError, ValueError)):
        parse_scoring_json(
            json.dumps(
                {
                    "direction": "sideways",
                    "confidence": 50,
                    "summary": "x",
                    "key_evidence": "y",
                    "event_type": "z",
                }
            )
        )


def test_neutral_does_not_alert():
    result = ScoringResult(
        direction="neutral",
        confidence=99,
        summary="Routine exhibit update.",
        key_evidence="Item 9.01",
        event_type="routine",
    )
    assert result.should_alert(65) is False


def test_scorer_retries_once_on_bad_json():
    calls = {"n": 0}

    class FakeClient:
        def chat_json(self, *, system: str, user: str, temperature: float = 0.1) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return "not-json"
            return json.dumps(
                {
                    "direction": "bearish",
                    "confidence": 70,
                    "summary": "Auditor resignation is concerning.",
                    "key_evidence": "Item 4.01",
                    "event_type": "auditor_change",
                }
            )

    scorer = FilingScorer(FakeClient(), alert_threshold=65)  # type: ignore[arg-type]
    outcome = scorer.score_filing_text(
        form_type="8-K",
        ticker="EXMP",
        company_name="Example",
        filing_text="Item 4.01 Changes in Registrant's Certifying Accountant.",
    )
    assert outcome.ok
    assert outcome.retried is True
    assert calls["n"] == 2
    assert outcome.result is not None
    assert outcome.result.direction == "bearish"
    assert scorer.should_alert(outcome.result) is True


def test_scorer_queues_concept_when_ollama_down():
    class DownClient:
        def chat_json(self, **kwargs) -> str:
            raise OllamaError("Ollama unreachable: connection refused")

    scorer = FilingScorer(DownClient(), alert_threshold=65)  # type: ignore[arg-type]
    outcome = scorer.score_filing_text(
        form_type="8-K",
        ticker="EXMP",
        company_name="Example",
        filing_text="text",
    )
    assert not outcome.ok
    assert outcome.error is not None
    assert "ollama_unavailable" in outcome.error


def test_ollama_client_json_mode_payload(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "direction": "neutral",
                            "confidence": 40,
                            "summary": "Routine.",
                            "key_evidence": "boilerplate",
                            "event_type": "routine",
                        }
                    ),
                }
            },
        )

    transport = httpx.MockTransport(handler)
    client = OllamaClient(
        base_url="http://ollama.test",
        model="qwen2.5:1.5b-instruct",
        transport=transport,
    )
    content = client.chat_json(system="sys", user="user")
    assert seen["path"] == "/api/chat"
    assert seen["body"]["format"] == "json"
    assert seen["body"]["model"] == "qwen2.5:1.5b-instruct"
    assert seen["body"]["stream"] is False
    parsed = parse_scoring_json(content)
    assert parsed.direction == "neutral"
    client.close()


def test_form4_rule_score_always_alerts():
    result = form4_rule_score(
        insider_name="Jane Officer",
        insider_role="Officer: CFO",
        shares=1000,
        price=250.5,
        total_value=250500,
    )
    assert result.direction == "bullish"
    assert result.confidence == 100
    assert result.event_type == "form4_open_market_buy"
    assert result.should_alert(65) is True


def test_processor_form4_rule_creates_alert(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "SECPulse Test test@example.com")
    from backend.config import Settings

    settings = Settings()  # type: ignore[call-arg]
    engine = create_engine(
        f"sqlite:///{tmp_path / 'a.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def session_factory() -> Session:
        return Session(engine)

    # Scorer should not be called for Form 4 rule path
    scorer = MagicMock()
    processor = FilingProcessor(
        settings, client=MagicMock(), session_factory=session_factory, scorer=scorer
    )

    with Session(engine) as session:
        filing = Filing(
            accession_number="0001318605-26-000010",
            form_type="4",
            cik="0001318605",
            company_name="Tesla, Inc.",
            ticker="TSLA",
            accepted_at=datetime.now(timezone.utc),
            filing_url="https://www.sec.gov/Archives/edgar/data/1318605/x-index.htm",
        )
        session.add(filing)
        session.commit()
        session.refresh(filing)
        session.add(
            Form4TransactionRow(
                filing_id=filing.id,
                accession_number=filing.accession_number,
                ticker="TSLA",
                insider_name="Jane Officer",
                insider_role="Officer: CFO",
                is_officer=True,
                is_director=False,
                transaction_code="P",
                shares=1000,
                price=250.5,
                total_value=250500,
                alert_by_rule=True,
            )
        )
        session.commit()
        fid = filing.id

    with Session(engine) as session:
        filing = session.get(Filing, fid)
        assert filing is not None
        processor.enqueue_filing(filing, form4_alert=True)
        session.add(filing)
        session.commit()

    assert processor.process_available() == 1
    scorer.score_filing_text.assert_not_called()

    with Session(engine) as session:
        alert = session.exec(select(Alert)).one()
        assert alert.source == "form4_rule"
        assert alert.direction == "bullish"
        assert alert.confidence == 100
        filing = session.get(Filing, fid)
        assert filing is not None
        assert filing.score_status == "alerted"


def test_processor_queues_when_ollama_down(
    fixtures_dir: Path, tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("SEC_USER_AGENT", "SECPulse Test test@example.com")
    from backend.config import Settings

    settings = Settings()  # type: ignore[call-arg]
    engine = create_engine(
        f"sqlite:///{tmp_path / 'b.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def session_factory() -> Session:
        return Session(engine)

    index = (fixtures_dir / "eightk_index.htm").read_text()
    primary = (fixtures_dir / "eightk_high_priority.htm").read_text()
    exhibit = (fixtures_dir / "eightk_exhibit_99_1.htm").read_text()

    def fake_get(url: str):
        resp = MagicMock()
        if url.endswith("-index.htm"):
            resp.text = index
        elif url.endswith("eightk_exhibit_99_1.htm"):
            resp.text = exhibit
        else:
            resp.text = primary
        return resp

    sec_client = MagicMock()
    sec_client.get.side_effect = fake_get

    class DownClient:
        def chat_json(self, **kwargs) -> str:
            raise OllamaError("down")

    scorer = FilingScorer(DownClient(), alert_threshold=65)  # type: ignore[arg-type]
    processor = FilingProcessor(
        settings, sec_client, session_factory, scorer=scorer
    )

    with Session(engine) as session:
        filing = Filing(
            accession_number="0000320193-26-000001",
            form_type="8-K",
            cik="0000320193",
            company_name="Apple Inc.",
            ticker="AAPL",
            accepted_at=datetime.now(timezone.utc),
            filing_url=(
                "https://www.sec.gov/Archives/edgar/data/320193/"
                "000032019326000001/0000320193-26-000001-index.htm"
            ),
        )
        session.add(filing)
        session.commit()
        session.refresh(filing)
        fid = filing.id
        processor.enqueue_filing(filing)
        session.add(filing)
        session.commit()

    assert processor.process_available() >= 1

    with Session(engine) as session:
        filing = session.get(Filing, fid)
        assert filing is not None
        assert filing.content_parsed is True
        assert filing.score_status == "awaiting_ollama"
        q = session.exec(
            select(ScoringQueueItem).where(ScoringQueueItem.status == "pending")
        ).one()
        assert q.filing_id == fid
        assert session.exec(select(Alert)).first() is None

    # Recovery: Ollama comes back on retry
    class UpClient:
        def chat_json(self, **kwargs) -> str:
            return json.dumps(
                {
                    "direction": "bullish",
                    "confidence": 88,
                    "summary": "Material acquisition closed.",
                    "key_evidence": "acquisition of Target LLC",
                    "event_type": "acquisition",
                }
            )

    processor.scorer = FilingScorer(UpClient(), alert_threshold=65)  # type: ignore[arg-type]
    assert processor.process_scoring_retries() == 1

    with Session(engine) as session:
        filing = session.get(Filing, fid)
        assert filing is not None
        assert filing.score_status == "alerted"
        alert = session.exec(select(Alert)).one()
        assert alert.direction == "bullish"
        assert alert.confidence == 88
        q = session.exec(select(ScoringQueueItem)).one()
        assert q.status == "done"
