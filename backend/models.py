"""SQLModel database models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Filing(SQLModel, table=True):
    """A single EDGAR filing discovered from the current Atom feed."""

    __tablename__ = "filings"

    id: Optional[int] = Field(default=None, primary_key=True)
    accession_number: str = Field(index=True, unique=True, max_length=32)
    form_type: str = Field(index=True, max_length=32)
    cik: str = Field(index=True, max_length=16)
    company_name: str = Field(default="", max_length=512)
    ticker: str = Field(index=True, max_length=16)
    accepted_at: datetime = Field(index=True)
    filing_url: str = Field(max_length=1024)
    ingested_at: datetime = Field(default_factory=_utcnow)
    # Stage 2: Form 4 parse status (None = not Form 4 / not attempted)
    form4_parsed: Optional[bool] = Field(default=None)
    # Stage 3: 8-K / 13D extraction status
    content_parsed: Optional[bool] = Field(default=None)
    queue_priority: Optional[int] = Field(default=None, index=True)
    queue_reason: Optional[str] = Field(default=None, max_length=128)
    # Stage 4: scoring
    # pending | scored | alerted | awaiting_ollama
    score_status: Optional[str] = Field(default=None, index=True, max_length=32)
    score_attempts: int = Field(default=0)
    last_score_error: Optional[str] = Field(default=None, max_length=512)


class Form4TransactionRow(SQLModel, table=True):
    """Parsed non-derivative Form 4 transaction."""

    __tablename__ = "form4_transactions"

    id: Optional[int] = Field(default=None, primary_key=True)
    filing_id: int = Field(index=True, foreign_key="filings.id")
    accession_number: str = Field(index=True, max_length=32)
    ticker: str = Field(default="", index=True, max_length=16)
    insider_name: str = Field(default="", max_length=256)
    insider_role: str = Field(default="", max_length=256)
    is_officer: bool = Field(default=False)
    is_director: bool = Field(default=False)
    transaction_code: str = Field(index=True, max_length=8)
    shares: float = Field(default=0.0)
    price: Optional[float] = Field(default=None)
    total_value: Optional[float] = Field(default=None)
    acquired_disposed: str = Field(default="", max_length=4)
    security_title: str = Field(default="", max_length=256)
    transaction_date: str = Field(default="", max_length=32)
    is_10b5_1: bool = Field(default=False)
    # Open-market buy (P) by officer/director — bypasses LLM scoring later
    alert_by_rule: bool = Field(default=False, index=True)
    skip_reason: Optional[str] = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=_utcnow)


class EightKExtraction(SQLModel, table=True):
    """Extracted 8-K items + Exhibit 99.1 / no-press-release flag."""

    __tablename__ = "eightk_extractions"

    id: Optional[int] = Field(default=None, primary_key=True)
    filing_id: int = Field(index=True, foreign_key="filings.id")
    accession_number: str = Field(index=True, max_length=32)
    ticker: str = Field(default="", index=True, max_length=16)
    item_numbers: str = Field(default="", max_length=256)  # comma-separated
    high_priority_items: str = Field(default="", max_length=256)
    has_exhibit_99_1: bool = Field(default=False)
    no_press_release: bool = Field(default=True)
    items_json: str = Field(default="")  # JSON list of {number,title,text}
    combined_text: str = Field(default="")
    truncated: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)


class SC13DExtraction(SQLModel, table=True):
    """Extracted SC 13D filer, stake %, and Item 4 purpose text."""

    __tablename__ = "sc13d_extractions"

    id: Optional[int] = Field(default=None, primary_key=True)
    filing_id: int = Field(index=True, foreign_key="filings.id")
    accession_number: str = Field(index=True, max_length=32)
    ticker: str = Field(default="", index=True, max_length=16)
    filer_name: str = Field(default="", max_length=512)
    stake_percent: Optional[float] = Field(default=None)
    item4_text: str = Field(default="")
    combined_text: str = Field(default="")
    truncated: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)


class Alert(SQLModel, table=True):
    """Persisted alert from Ollama score or Form 4 rule."""

    __tablename__ = "alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    filing_id: int = Field(index=True, foreign_key="filings.id")
    accession_number: str = Field(index=True, max_length=32)
    ticker: str = Field(index=True, max_length=16)
    form_type: str = Field(default="", max_length=32)
    company_name: str = Field(default="", max_length=512)
    direction: str = Field(index=True, max_length=16)
    confidence: int = Field(default=0)
    summary: str = Field(default="")
    key_evidence: str = Field(default="")
    event_type: str = Field(default="", max_length=128)
    # "ollama" | "form4_rule"
    source: str = Field(default="ollama", index=True, max_length=32)
    created_at: datetime = Field(default_factory=_utcnow)


class ScoringQueueItem(SQLModel, table=True):
    """Durable retry queue when Ollama is down/slow or JSON invalid after retry."""

    __tablename__ = "scoring_queue"

    id: Optional[int] = Field(default=None, primary_key=True)
    filing_id: int = Field(index=True, foreign_key="filings.id")
    accession_number: str = Field(index=True, max_length=32)
    form_type: str = Field(default="", max_length=32)
    ticker: str = Field(default="", max_length=16)
    company_name: str = Field(default="", max_length=512)
    filing_text: str = Field(default="")
    priority: int = Field(default=0, index=True)
    attempts: int = Field(default=0)
    last_error: Optional[str] = Field(default=None, max_length=512)
    # pending | done
    status: str = Field(default="pending", index=True, max_length=16)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
