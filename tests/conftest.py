"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def sample_atom_xml(fixtures_dir: Path) -> str:
    return (fixtures_dir / "sample_atom.xml").read_text(encoding="utf-8")


@pytest.fixture
def company_tickers_payload(fixtures_dir: Path) -> dict:
    import json

    return json.loads((fixtures_dir / "company_tickers.json").read_text(encoding="utf-8"))
