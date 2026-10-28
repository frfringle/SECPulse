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
