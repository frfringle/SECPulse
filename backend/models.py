"""SQLModel database models for Stage 1 ingestion."""

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
