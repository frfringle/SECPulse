"""Tests for SEC Atom feed parsing."""

from __future__ import annotations

from datetime import timezone

from backend.config import WATCHED_FORMS
from backend.sec.atom import parse_atom_feed, parse_title


def test_parse_title_8k():
    result = parse_title("8-K - Apple Inc. (0000320193) (Filer)")
    assert result is not None
    form, company, cik = result
    assert form == "8-K"
    assert company == "Apple Inc."
    assert cik == "0000320193"


def test_parse_title_sc13d_amendment():
    result = parse_title("SC 13D/A - Berkshire Hathaway Inc (0001067983) (Filer)")
    assert result is not None
    form, company, cik = result
    assert form == "SC 13D/A"
    assert company == "Berkshire Hathaway Inc"
    assert cik == "0001067983"


def test_parse_atom_filters_watched_forms(sample_atom_xml: str):
    filings = parse_atom_feed(sample_atom_xml)
    forms = {f.form_type for f in filings}
    assert forms <= WATCHED_FORMS
    assert "10-Q" not in forms
    assert "3" not in forms
    assert forms == {"8-K", "4", "SC 13D", "SC 13D/A", "8-K/A"}


def test_parse_atom_extracts_fields(sample_atom_xml: str):
    filings = parse_atom_feed(sample_atom_xml)
    by_accession = {f.accession_number: f for f in filings}

    apple = by_accession["0000320193-26-000001"]
    assert apple.form_type == "8-K"
    assert apple.cik == "0000320193"
    assert apple.company_name == "Apple Inc."
    assert "0000320193-26-000001-index.htm" in apple.filing_url
    assert apple.accepted_at.tzinfo == timezone.utc

    tesla = by_accession["0001318605-26-000010"]
    assert tesla.form_type == "4"
    assert tesla.cik == "0001318605"
    assert tesla.company_name == "Tesla, Inc."


def test_parse_atom_count(sample_atom_xml: str):
    filings = parse_atom_feed(sample_atom_xml)
    # 5 watched, 2 filtered (10-Q, 3)
    assert len(filings) == 5
