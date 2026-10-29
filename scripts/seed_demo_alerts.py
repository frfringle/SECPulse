#!/usr/bin/env python3
"""Seed a few demo filings/alerts for UI smoke testing."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SEC_USER_AGENT", "SECPulse Demo demo@example.com")
os.environ.setdefault("SECPULSE_DISABLE_BACKGROUND", "1")

from sqlmodel import select

from backend.config import get_settings
from backend.db import init_db, session_scope
from backend.models import Alert, Filing

get_settings.cache_clear()


def main() -> None:
    init_db()
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        if list(session.exec(select(Alert).limit(1)).all()):
            print("Alerts already present — skipping seed")
            return

        samples = [
            {
                "ticker": "AAPL",
                "company": "Apple Inc.",
                "form": "8-K",
                "direction": "bullish",
                "confidence": 82,
                "summary": "Entered a material revolving credit facility and closed a tuck-in acquisition.",
                "evidence": "acquisition of Target LLC for approximately $120 million",
                "event": "acquisition",
                "bucket": "mid",
                "pct": 1.8,
                "no_pr": False,
                "source": "ollama",
            },
            {
                "ticker": "TSLA",
                "company": "Tesla, Inc.",
                "form": "4",
                "direction": "bullish",
                "confidence": 100,
                "summary": "Jane Officer (CFO) open-market bought 1,000 shares at $250.50.",
                "evidence": "Form 4 code P by Officer: CFO: 1000 shares",
                "event": "form4_open_market_buy",
                "bucket": "mid",
                "pct": 0.6,
                "no_pr": None,
                "source": "form4_rule",
            },
            {
                "ticker": "EXMP",
                "company": "Example Corp",
                "form": "SC 13D",
                "direction": "bullish",
                "confidence": 78,
                "summary": "Activist Partners disclosed an 8.4% stake and flagged board engagement.",
                "evidence": "may engage in discussions with management and the Board",
                "event": "activist_13d",
                "bucket": "small",
                "pct": 4.2,
                "no_pr": None,
                "source": "ollama",
            },
            {
                "ticker": "MSFT",
                "company": "Microsoft Corp",
                "form": "8-K",
                "direction": "bearish",
                "confidence": 71,
                "summary": "Auditor change disclosed without an accompanying press release.",
                "evidence": "Item 4.01 Changes in Registrant's Certifying Accountant",
                "event": "auditor_change",
                "bucket": "large",
                "pct": -1.1,
                "no_pr": True,
                "source": "ollama",
            },
        ]

        for i, s in enumerate(samples):
            accepted = now - timedelta(minutes=30 + i * 12)
            filing = Filing(
                accession_number=f"0000000000-26-{i + 1:06d}",
                form_type=s["form"],
                cik=f"{320193 + i:010d}",
                company_name=s["company"],
                ticker=s["ticker"],
                accepted_at=accepted,
                filing_url=(
                    f"https://www.sec.gov/Archives/edgar/data/{320193 + i}/"
                    f"000000000026{i + 1:06d}/0000000000-26-{i + 1:06d}-index.htm"
                ),
                content_parsed=True,
                score_status="alerted",
            )
            session.add(filing)
            session.flush()
            session.add(
                Alert(
                    filing_id=filing.id,
                    accession_number=filing.accession_number,
                    ticker=s["ticker"],
                    form_type=s["form"],
                    company_name=s["company"],
                    direction=s["direction"],
                    confidence=s["confidence"],
                    summary=s["summary"],
                    key_evidence=s["evidence"],
                    event_type=s["event"],
                    source=s["source"],
                    created_at=accepted + timedelta(minutes=2),
                    latency_seconds=120 + i * 15,
                    price_at_alert=100 + i * 10,
                    price_at_accepted=98 + i * 10,
                    pct_change_since_accepted=s["pct"],
                    market_cap_bucket=s["bucket"],
                    no_press_release=s["no_pr"],
                )
            )
        session.commit()
        print(f"Seeded {len(samples)} demo alerts")


if __name__ == "__main__":
    main()
