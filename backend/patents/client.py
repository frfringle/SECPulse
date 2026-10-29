"""USPTO Open Data Portal (ODP) HTTP client."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx

from backend.sec.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

ODP_SEARCH_URL = "https://api.uspto.gov/api/v1/patent/applications/search"


class UsptoClient:
    """Thin ODP search wrapper. Inject `search_fn` in tests to avoid live calls."""

    def __init__(
        self,
        api_key: str,
        *,
        rate_limiter: RateLimiter | None = None,
        max_per_second: float = 1.0,
        timeout_seconds: float = 30.0,
        search_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        if not (api_key or "").strip():
            raise ValueError("USPTO_API_KEY is required for UsptoClient")
        self.api_key = api_key.strip()
        self.rate_limiter = rate_limiter or RateLimiter(max_per_second)
        self._search_fn = search_fn
        self._http: httpx.Client | None = None
        if search_fn is None:
            self._http = httpx.Client(
                timeout=timeout_seconds,
                headers={
                    "X-API-KEY": self.api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    def search(self, body: dict[str, Any]) -> dict[str, Any]:
        if self._search_fn is not None:
            return self._search_fn(body)
        assert self._http is not None
        self.rate_limiter.acquire()
        resp = self._http.post(ODP_SEARCH_URL, json=body)
        if resp.status_code in {403, 429}:
            logger.warning("USPTO rate/auth status=%s body=%s", resp.status_code, resp.text[:200])
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()

    def search_recent_for_assignee(
        self,
        assignee: str,
        *,
        since: date | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Search recent applications/grants mentioning an assignee name."""
        since = since or (date.today() - timedelta(days=14))
        # Prefer applicant / assignee name fields; fall back to free-text if needed.
        q = (
            f'(applicationMetaData.applicantBag:"{assignee}" OR '
            f'applicationMetaData.firstApplicantName:"{assignee}" OR '
            f'"{assignee}")'
        )
        body: dict[str, Any] = {
            "q": q,
            "filters": [
                {
                    "name": "applicationMetaData.filingDate",
                    "value": [f"{since.isoformat()}/"],
                }
            ],
            "rangeFilters": [
                {
                    "field": "applicationMetaData.filingDate",
                    "valueFrom": since.isoformat(),
                    "valueTo": date.today().isoformat(),
                }
            ],
            "pagination": {"offset": 0, "limit": limit},
            "fields": [
                "applicationNumberText",
                "applicationMetaData",
                "patentNumber",
                "grantDate",
            ],
        }
        try:
            data = self.search(body)
        except Exception as exc:  # noqa: BLE001
            # Retry with a simpler free-text query if structured filters reject.
            logger.debug("USPTO structured search failed (%s); retrying simple q", exc)
            data = self.search(
                {
                    "q": assignee,
                    "pagination": {"offset": 0, "limit": limit},
                }
            )
        return _extract_patent_bags(data)


def _extract_patent_bags(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("patentFileWrapperDataBag", "patentData", "patents", "results", "data"):
        bag = data.get(key)
        if isinstance(bag, list):
            return [x for x in bag if isinstance(x, dict)]
    # Some responses nest once more
    count_bag = data.get("count")
    if isinstance(data.get("patentFileWrapperDataBag"), dict):
        inner = data["patentFileWrapperDataBag"].get("data")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    if count_bag is not None and isinstance(data.get("patentFileWrapperDataBag"), list):
        return data["patentFileWrapperDataBag"]
    return []


def parse_odp_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single ODP search hit into flat fields used by the poller."""
    meta = raw.get("applicationMetaData") or {}
    if not isinstance(meta, dict):
        meta = {}

    app_no = str(
        raw.get("applicationNumberText")
        or meta.get("applicationNumberText")
        or raw.get("applicationNumber")
        or ""
    ).strip()
    patent_no = str(
        raw.get("patentNumber")
        or meta.get("patentNumber")
        or ""
    ).strip() or None
    title = str(
        meta.get("inventionTitle")
        or raw.get("inventionTitle")
        or ""
    ).strip()
    status = str(
        meta.get("applicationStatusDescriptionText")
        or meta.get("applicationStatusLabelName")
        or raw.get("applicationStatusDescriptionText")
        or ""
    ).strip() or None

    assignees: list[str] = []
    for key in ("applicantBag", "applicants", "assignees"):
        bag = meta.get(key) or raw.get(key)
        if isinstance(bag, list):
            for item in bag:
                if isinstance(item, dict):
                    name = (
                        item.get("applicantNameText")
                        or item.get("assigneeNameText")
                        or item.get("name")
                        or ""
                    )
                    if name:
                        assignees.append(str(name).strip())
                elif isinstance(item, str) and item.strip():
                    assignees.append(item.strip())
        elif isinstance(bag, str) and bag.strip():
            assignees.append(bag.strip())
    first = meta.get("firstApplicantName") or raw.get("firstApplicantName")
    if first and str(first).strip():
        assignees.insert(0, str(first).strip())
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for a in assignees:
        k = a.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(a)

    grant_raw = meta.get("grantDate") or raw.get("grantDate")
    filing_raw = meta.get("filingDate") or meta.get("applicationFilingDate") or raw.get(
        "applicationFilingDate"
    )
    pub_raw = meta.get("earliestPublicationDate") or raw.get("publicationDate")

    def _parse_dt(value: object) -> Optional[datetime]:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            try:
                return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return None

    grant_at = _parse_dt(grant_raw)
    filing_at = _parse_dt(filing_raw)
    pub_at = _parse_dt(pub_raw)

    if patent_no or grant_at:
        event_type = "grant"
        event_at = grant_at or pub_at or filing_at
    else:
        event_type = "application_published"
        event_at = pub_at or filing_at

    status_l = (status or "").lower()
    if any(x in status_l for x in ("abandon", "allowance", "allowed", "issued")) and event_type != "grant":
        if "abandon" in status_l or "allow" in status_l:
            event_type = "status_change"

    uspto_url = (
        f"https://patentcenter.uspto.gov/applications/{app_no}"
        if app_no
        else "https://data.uspto.gov/"
    )
    google = None
    if patent_no:
        digits = "".join(c for c in patent_no if c.isalnum())
        google = f"https://patents.google.com/patent/US{digits}/en"

    return {
        "application_number": app_no,
        "patent_number": patent_no,
        "title": title,
        "assignees": uniq,
        "status_label": status,
        "event_type": event_type,
        "event_at": event_at,
        "uspto_url": uspto_url,
        "google_patents_url": google,
        "raw": raw,
    }
