"""Compute price enrichment fields for alerts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from backend.prices.yfinance_client import YFinanceClient, market_cap_bucket

logger = logging.getLogger(__name__)


@dataclass
class PriceEnrichment:
    latency_seconds: Optional[float] = None
    price_at_alert: Optional[float] = None
    price_at_accepted: Optional[float] = None
    pct_change_since_accepted: Optional[float] = None
    market_cap: Optional[float] = None
    market_cap_bucket: Optional[str] = None
    no_press_release: Optional[bool] = None
    enrichment_error: Optional[str] = None


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def enrich_alert_fields(
    *,
    ticker: str,
    accepted_at: datetime,
    alert_at: Optional[datetime] = None,
    no_press_release: Optional[bool] = None,
    client: Optional[YFinanceClient] = None,
) -> PriceEnrichment:
    """Build enrichment payload. Never raises — failures set enrichment_error."""
    alert_at = _ensure_aware(alert_at or datetime.now(timezone.utc))
    accepted = _ensure_aware(accepted_at)
    latency = max(0.0, (alert_at - accepted).total_seconds())

    yf = client or YFinanceClient()
    out = PriceEnrichment(
        latency_seconds=latency,
        no_press_release=no_press_release,
    )

    try:
        snap = yf.get_snapshot(ticker)
        if snap.error:
            out.enrichment_error = snap.error
        out.price_at_alert = snap.price
        out.market_cap = snap.market_cap
        out.market_cap_bucket = market_cap_bucket(snap.market_cap)

        accepted_px = yf.get_price_near(ticker, accepted)
        out.price_at_accepted = accepted_px

        if (
            out.price_at_alert is not None
            and accepted_px is not None
            and accepted_px != 0
        ):
            out.pct_change_since_accepted = round(
                ((out.price_at_alert - accepted_px) / accepted_px) * 100.0,
                4,
            )
    except Exception as exc:  # noqa: BLE001 — pipeline must not crash
        logger.warning("Price enrichment failed ticker=%s error=%s", ticker, exc)
        out.enrichment_error = str(exc)[:300]

    return out
