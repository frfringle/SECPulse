"""CIK → ticker mapping with daily on-disk cache of company_tickers.json."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from backend.config import COMPANY_TICKERS_URL, PROJECT_ROOT
from backend.sec.client import SecClient

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 24 * 60 * 60  # refresh at most once per day


def normalize_cik(cik: str | int) -> str:
    """Normalize CIK to a zero-padded 10-digit string (SEC convention)."""
    digits = "".join(ch for ch in str(cik).strip() if ch.isdigit())
    if not digits:
        return ""
    return digits.zfill(10)


def build_cik_to_ticker(payload: dict[str, Any]) -> dict[str, str]:
    """Build CIK→ticker map from SEC company_tickers.json structure.

    Payload shape: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ...}
    """
    mapping: dict[str, str] = {}
    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        cik_raw = entry.get("cik_str")
        ticker = entry.get("ticker")
        if cik_raw is None or not ticker:
            continue
        cik = normalize_cik(cik_raw)
        if cik:
            # Prefer first-seen ticker if duplicates (some CIKs have multiple)
            mapping.setdefault(cik, str(ticker).upper())
    return mapping


class TickerCache:
    """Loads and caches the SEC company ticker JSON locally for 24h."""

    def __init__(
        self,
        client: SecClient,
        cache_path: Path | None = None,
        ttl_seconds: int = CACHE_TTL_SECONDS,
    ) -> None:
        self.client = client
        self.cache_path = cache_path or (PROJECT_ROOT / "data" / "ticker_cache.json")
        self.ttl_seconds = ttl_seconds
        self._map: dict[str, str] = {}
        self._loaded_at: float = 0.0

    @property
    def mapping(self) -> dict[str, str]:
        return self._map

    def _cache_is_fresh(self) -> bool:
        if not self.cache_path.exists():
            return False
        age = time.time() - self.cache_path.stat().st_mtime
        return age < self.ttl_seconds

    def _read_disk(self) -> dict[str, Any]:
        with self.cache_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write_disk(self, payload: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        tmp.replace(self.cache_path)

    def load(self, force_refresh: bool = False) -> dict[str, str]:
        """Return CIK→ticker map, refreshing from SEC when cache is stale."""
        payload: Optional[dict[str, Any]] = None

        if not force_refresh and self._cache_is_fresh():
            try:
                payload = self._read_disk()
                logger.info("Loaded ticker cache from disk path=%s", self.cache_path)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Corrupt ticker cache; will refetch: %s", exc)

        if payload is None:
            try:
                response = self.client.get(COMPANY_TICKERS_URL)
                payload = response.json()
                self._write_disk(payload)
                logger.info(
                    "Fetched company_tickers.json entries=%s",
                    len(payload) if isinstance(payload, dict) else "?",
                )
            except Exception as exc:  # noqa: BLE001 — graceful SEC failure
                logger.error("Failed to fetch company tickers: %s", exc)
                if self.cache_path.exists():
                    logger.warning("Falling back to stale ticker cache")
                    payload = self._read_disk()
                else:
                    self._map = {}
                    return self._map

        assert payload is not None
        self._map = build_cik_to_ticker(payload)
        self._loaded_at = time.time()
        logger.info("Ticker map ready size=%s", len(self._map))
        return self._map

    def lookup(self, cik: str | int) -> Optional[str]:
        """Return ticker for CIK, or None if unknown."""
        if not self._map:
            self.load()
        return self._map.get(normalize_cik(cik))
