"""Tests for 8-K item extraction, Exhibit 99.1, and no-press-release flag."""

from __future__ import annotations

from pathlib import Path

from backend.sec.eightk import extract_eightk_items, parse_eightk
from backend.sec.priority import HIGH_PRIORITY_8K_ITEMS
from backend.sec.textutil import estimate_tokens, truncate_to_token_budget


def test_extract_high_priority_items(fixtures_dir: Path):
    html = (fixtures_dir / "eightk_high_priority.htm").read_text()
    items = extract_eightk_items(html)
    numbers = [i.number for i in items]
    assert "1.01" in numbers
    assert "2.01" in numbers
    assert "5.02" in numbers
    assert "9.01" in numbers

    by_num = {i.number: i for i in items}
    assert by_num["1.01"].is_high_priority is True
    assert "Credit Agreement" in by_num["1.01"].text
    assert by_num["2.01"].is_high_priority is True
    assert "Target LLC" in by_num["2.01"].text
    assert by_num["5.02"].is_high_priority is True
    assert by_num["9.01"].is_high_priority is False
    assert set(numbers) & HIGH_PRIORITY_8K_ITEMS == {"1.01", "2.01", "5.02"}


def test_parse_eightk_includes_exhibit_99_1(fixtures_dir: Path):
    primary = (fixtures_dir / "eightk_high_priority.htm").read_text()
    exhibit = (fixtures_dir / "eightk_exhibit_99_1.htm").read_text()
    result = parse_eightk(
        primary,
        exhibit_99_1_html=exhibit,
        exhibit_99_1_listed=True,
        token_budget=4000,
    )
    assert result.has_exhibit_99_1 is True
    assert result.no_press_release is False
    assert "FOR IMMEDIATE RELEASE" in result.exhibit_99_1_text
    assert "Exhibit 99.1" in result.combined_text
    assert result.high_priority_item_numbers == ["1.01", "2.01", "5.02"]
    assert result.truncated is False


def test_parse_eightk_flags_no_press_release(fixtures_dir: Path):
    primary = (fixtures_dir / "eightk_no_press_release.htm").read_text()
    result = parse_eightk(
        primary,
        exhibit_99_1_html=None,
        exhibit_99_1_listed=False,
        token_budget=4000,
    )
    assert result.no_press_release is True
    assert result.has_exhibit_99_1 is False
    assert "no press release" in result.combined_text.lower()
    assert [i.number for i in result.items] == ["2.02", "9.01"]
    assert result.has_high_priority is False


def test_truncate_to_token_budget():
    text = "word " * 5000
    truncated, was = truncate_to_token_budget(text, token_budget=50)
    assert was is True
    assert estimate_tokens(truncated) <= 60  # allowance for truncation marker
    assert truncated.endswith("…[truncated]")
    same, was2 = truncate_to_token_budget("short", 100)
    assert was2 is False
    assert same == "short"
