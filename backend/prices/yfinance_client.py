"""Small yfinance wrapper with per-ticker 60s caching and soft failures."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60.0


@dataclass(frozen=True)
class TickerSnapshot:
    ticker: str
    price: Optional[float]
    market_cap: Optional[float]
    currency: str = "USD"
    fetched_at: float = 0.0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.price is not None


def market_cap_bucket(market_cap: Optional[float]) -> Optional[str]:
    """Map market cap to small / mid / large."""
    if market_cap is None or market_cap <= 0:
        return None
    if market_cap < 2_000_000_000:
        return "small"
    if market_cap < 10_000_000_000:
        return "mid"
    return "large"


class YFinanceClient:
    """Cached lookups for last price, historical close, and market cap."""

    def __init__(
        self,
        ttl_seconds: float = CACHE_TTL_SECONDS,
        fetcher: Optional[Callable[[str], dict[str, Any]]] = None,
        history_fetcher: Optional[
            Callable[[str, datetime], Optional[float]]
        ] = None,
        series_fetcher: Optional[
            Callable[[str, str, str], list[dict[str, Any]]]
        ] = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._fetcher = fetcher or _default_fetch_snapshot
        self._history_fetcher = history_fetcher or _default_fetch_price_at
        self._series_fetcher = series_fetcher or _default_fetch_series
        self._cache: dict[str, TickerSnapshot] = {}
        self._hist_cache: dict[tuple[str, str], tuple[float, Optional[float]]] = {}
        self._series_cache: dict[tuple[str, str, str], tuple[float, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

    def get_snapshot(self, ticker: str) -> TickerSnapshot:
        key = (ticker or "").strip().upper()
        if not key:
            return TickerSnapshot(
                ticker="", price=None, market_cap=None, error="empty_ticker"
            )

        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and (now - cached.fetched_at) < self.ttl_seconds:
                return cached

        try:
            data = self._fetcher(key)
            snap = TickerSnapshot(
                ticker=key,
                price=_as_float(data.get("price")),
                market_cap=_as_float(data.get("market_cap")),
                currency=str(data.get("currency") or "USD"),
                fetched_at=now,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001 — never crash callers
            logger.warning("yfinance snapshot failed ticker=%s error=%s", key, exc)
            snap = TickerSnapshot(
                ticker=key,
                price=None,
                market_cap=None,
                fetched_at=now,
                error=str(exc)[:300],
            )

        with self._lock:
            self._cache[key] = snap
        return snap

    def get_price_near(self, ticker: str, when: datetime) -> Optional[float]:
        """Best-effort price at/near `when` (UTC). Cached 60s per ticker+day."""
        key = (ticker or "").strip().upper()
        if not key:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        else:
            when = when.astimezone(timezone.utc)
        day_key = when.date().isoformat()
        cache_key = (key, day_key)

        now = time.monotonic()
        with self._lock:
            hit = self._hist_cache.get(cache_key)
            if hit is not None and (now - hit[0]) < self.ttl_seconds:
                return hit[1]

        try:
            price = self._history_fetcher(key, when)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "yfinance history failed ticker=%s when=%s error=%s",
                key,
                day_key,
                exc,
            )
            price = None

        with self._lock:
            self._hist_cache[cache_key] = (now, price)
        return price

    def get_history(
        self,
        ticker: str,
        *,
        period: str = "5d",
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        """Return OHLCV points for charts. Soft-fails to []."""
        key = (ticker or "").strip().upper()
        if not key:
            return []
        cache_key = (key, period, interval)
        now = time.monotonic()
        with self._lock:
            hit = self._series_cache.get(cache_key)
            if hit is not None and (now - hit[0]) < self.ttl_seconds:
                return list(hit[1])

        try:
            points = self._series_fetcher(key, period, interval)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "yfinance series failed ticker=%s period=%s error=%s",
                key,
                period,
                exc,
            )
            points = []

        with self._lock:
            self._series_cache[cache_key] = (now, points)
        return list(points)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hist_cache.clear()
            self._series_cache.clear()


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _default_fetch_snapshot(ticker: str) -> dict[str, Any]:
    import yfinance as yf  # lazy import — keeps tests light if unused

    t = yf.Ticker(ticker)
    price = None
    market_cap = None
    currency = "USD"
    try:
        fast = getattr(t, "fast_info", None)
        if fast is not None:
            price = getattr(fast, "last_price", None) or fast.get("last_price")  # type: ignore[union-attr]
            market_cap = getattr(fast, "market_cap", None) or fast.get("market_cap")  # type: ignore[union-attr]
            currency = (
                getattr(fast, "currency", None) or fast.get("currency") or "USD"  # type: ignore[union-attr]
            )
    except Exception:  # noqa: BLE001
        pass

    if price is None or market_cap is None:
        info = {}
        try:
            info = t.info or {}
        except Exception:  # noqa: BLE001
            info = {}
        price = price or info.get("currentPrice") or info.get("regularMarketPrice")
        market_cap = market_cap or info.get("marketCap")
        currency = info.get("currency") or currency

    if price is None:
        # Last resort: recent 1d history
        hist = t.history(period="1d")
        if hist is not None and not hist.empty:
            price = float(hist["Close"].iloc[-1])

    if price is None and market_cap is None:
        raise RuntimeError(f"no yfinance data for {ticker}")

    return {"price": price, "market_cap": market_cap, "currency": currency}


def _default_fetch_price_at(ticker: str, when: datetime) -> Optional[float]:
    import yfinance as yf

    start = (when - timedelta(days=5)).date()
    end = (when + timedelta(days=2)).date()
    t = yf.Ticker(ticker)
    hist = t.history(start=start.isoformat(), end=end.isoformat())
    if hist is None or hist.empty:
        return None
    # Prefer close on/before the filing day
    target = when.date()
    closes: list[tuple[Any, float]] = []
    for idx, row in hist.iterrows():
        try:
            d = idx.to_pydatetime().date() if hasattr(idx, "to_pydatetime") else idx
        except Exception:  # noqa: BLE001
            continue
        closes.append((d, float(row["Close"])))
    if not closes:
        return None
    on_or_before = [c for c in closes if c[0] <= target]
    if on_or_before:
        return on_or_before[-1][1]
    return closes[0][1]


def _default_fetch_series(
    ticker: str, period: str, interval: str
) -> list[dict[str, Any]]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    hist = t.history(period=period, interval=interval)
    if hist is None or hist.empty:
        return []
    points: list[dict[str, Any]] = []
    for idx, row in hist.iterrows():
        try:
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            iso = ts.astimezone(timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            iso = str(idx)
        points.append(
            {
                "t": iso,
                "open": _as_float(row.get("Open")),
                "high": _as_float(row.get("High")),
                "low": _as_float(row.get("Low")),
                "close": _as_float(row.get("Close")),
                "volume": _as_float(row.get("Volume")),
            }
        )
    return points
