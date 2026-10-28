"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pytest

from backend.prices.yfinance_client import YFinanceClient
from backend.scoring.alerts import set_yf_client

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


@pytest.fixture(autouse=True)
def _mock_yfinance_default():
    """Avoid live Yahoo calls during tests; individual tests may override."""

    def fetcher(ticker: str) -> dict[str, Any]:
        return {
            "price": 100.0,
            "market_cap": 5_000_000_000,
            "currency": "USD",
        }

    def history_fetcher(ticker: str, when: datetime) -> Optional[float]:
        return 95.0

    client = YFinanceClient(fetcher=fetcher, history_fetcher=history_fetcher)
    set_yf_client(client)
    yield client
    set_yf_client(None)
