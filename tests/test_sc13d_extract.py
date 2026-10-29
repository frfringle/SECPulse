"""Tests for SC 13D filer / stake % / Item 4 extraction."""

from __future__ import annotations

from pathlib import Path

from backend.sec.sc13d import parse_sc13d


def test_parse_sc13d_filer_stake_item4(fixtures_dir: Path):
    html = (fixtures_dir / "sc13d_sample.htm").read_text()
    result = parse_sc13d(html, token_budget=4000)

    assert result.filer_name == "Activist Partners LP"
    assert result.stake_percent == 8.4
    assert "investment purposes" in result.item4_text.lower()
    assert "Board" in result.item4_text
    assert "Item 5" not in result.item4_text
    assert "Filer: Activist Partners LP" in result.combined_text
    assert "8.4" in result.combined_text
    assert result.truncated is False


def test_parse_sc13d_truncates_long_item4():
    long_body = "purpose " * 5000
    doc = f"""
    Name of Reporting Persons
    Long Winded Fund LLC

    Percent of Class Represented by Amount in Row (11)
    12.5%

    Item 4. Purpose of Transaction.
    {long_body}
    Item 5. Interest in Securities of the Issuer.
    Owns 12.5 percent.
    """
    result = parse_sc13d(doc, token_budget=100)
    assert result.filer_name == "Long Winded Fund LLC"
    assert result.stake_percent == 12.5
    assert result.truncated is True
    assert "…[truncated]" in result.combined_text
