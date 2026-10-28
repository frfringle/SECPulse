"""Tests for CIK → ticker mapping and daily cache."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from backend.sec.ticker_cache import (
    TickerCache,
    build_cik_to_ticker,
    normalize_cik,
)


def test_normalize_cik_pads_and_strips():
    assert normalize_cik(320193) == "0000320193"
    assert normalize_cik("320193") == "0000320193"
    assert normalize_cik("0000320193") == "0000320193"
    assert normalize_cik("CIK 1318605") == "0001318605"
    assert normalize_cik("") == ""


def test_build_cik_to_ticker(company_tickers_payload: dict):
    mapping = build_cik_to_ticker(company_tickers_payload)
    assert mapping["0000320193"] == "AAPL"
    assert mapping["0001318605"] == "TSLA"
    assert mapping["0000789019"] == "MSFT"
    assert mapping["0001067983"] == "BRK-B"
    assert "0009999999" not in mapping


def test_ticker_cache_loads_from_disk(
    company_tickers_payload: dict,
    tmp_path: Path,
):
    cache_file = tmp_path / "ticker_cache.json"
    cache_file.write_text(json.dumps(company_tickers_payload), encoding="utf-8")

    client = MagicMock()
    cache = TickerCache(client=client, cache_path=cache_file, ttl_seconds=86400)
    mapping = cache.load()

    client.get.assert_not_called()
    assert cache.lookup(320193) == "AAPL"
    assert cache.lookup("0001318605") == "TSLA"
    assert cache.lookup(9999999) is None
    assert len(mapping) == 5


def test_ticker_cache_fetches_when_missing(
    company_tickers_payload: dict,
    tmp_path: Path,
):
    cache_file = tmp_path / "ticker_cache.json"
    response = MagicMock()
    response.json.return_value = company_tickers_payload

    client = MagicMock()
    client.get.return_value = response

    cache = TickerCache(client=client, cache_path=cache_file, ttl_seconds=86400)
    mapping = cache.load()

    client.get.assert_called_once()
    assert cache_file.exists()
    assert mapping["0000320193"] == "AAPL"


def test_ticker_cache_skips_refresh_when_fresh(
    company_tickers_payload: dict,
    tmp_path: Path,
):
    cache_file = tmp_path / "ticker_cache.json"
    cache_file.write_text(json.dumps(company_tickers_payload), encoding="utf-8")

    client = MagicMock()
    cache = TickerCache(client=client, cache_path=cache_file, ttl_seconds=86400)
    cache.load()
    cache.load()  # second call should still hit disk, not network

    client.get.assert_not_called()
