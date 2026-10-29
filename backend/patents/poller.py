"""Poll USPTO ODP for new applications / grants mapped to tickers."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlmodel import Session, select

from backend.models import PatentEvent
from backend.patents.assignee_map import AssigneeMap
from backend.patents.client import UsptoClient, parse_odp_record

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


def make_dedupe_key(application_number: str, event_type: str, patent_number: str | None) -> str:
    pn = (patent_number or "").strip()
    return f"{application_number.strip()}|{event_type}|{pn}"


class PatentPoller:
    """Walk assignee aliases, search ODP, persist new PatentEvent rows."""

    def __init__(
        self,
        *,
        client: UsptoClient,
        assignee_map: AssigneeMap,
        session_factory: SessionFactory,
        lookback_days: int = 14,
        per_assignee_limit: int = 15,
    ) -> None:
        self.client = client
        self.assignee_map = assignee_map
        self.session_factory = session_factory
        self.lookback_days = lookback_days
        self.per_assignee_limit = per_assignee_limit
        self.last_poll_at: Optional[datetime] = None
        self.last_poll_inserted: int = 0
        self.last_poll_error: Optional[str] = None

    def poll_once(self) -> int:
        inserted = 0
        self.last_poll_error = None
        since = date.today() - timedelta(days=self.lookback_days)
        aliases = list(self.assignee_map._by_norm.values())
        # Unique tickers → one search per canonical alias string
        seen_alias: set[str] = set()
        try:
            for hit in aliases:
                alias = hit.matched_alias
                if alias.lower() in seen_alias:
                    continue
                seen_alias.add(alias.lower())
                try:
                    bags = self.client.search_recent_for_assignee(
                        alias,
                        since=since,
                        limit=self.per_assignee_limit,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("USPTO search failed assignee=%s err=%s", alias, exc)
                    continue
                for raw in bags:
                    n = self._ingest_raw(raw, preferred_ticker=hit.ticker, preferred_company=hit.company_name)
                    inserted += n
        except Exception as exc:  # noqa: BLE001
            self.last_poll_error = str(exc)
            logger.exception("Patent poll failed: %s", exc)
        self.last_poll_at = datetime.now(timezone.utc)
        self.last_poll_inserted = inserted
        logger.info("Patent poll complete inserted=%s aliases=%s", inserted, len(seen_alias))
        return inserted

    def ingest_records(self, records: list[dict[str, Any]]) -> int:
        """Test helper: ingest already-normalized or raw ODP bags."""
        inserted = 0
        for raw in records:
            inserted += self._ingest_raw(raw)
        return inserted

    def _ingest_raw(
        self,
        raw: dict[str, Any],
        *,
        preferred_ticker: str | None = None,
        preferred_company: str | None = None,
    ) -> int:
        if "applicationNumberText" in raw or "applicationMetaData" in raw:
            parsed = parse_odp_record(raw)
        else:
            parsed = dict(raw)
            if "assignees" not in parsed and parsed.get("assignee"):
                parsed["assignees"] = [str(parsed["assignee"])]

        app_no = str(parsed.get("application_number") or "").strip()
        if not app_no:
            return 0
        event_type = str(parsed.get("event_type") or "application_published")
        patent_no = parsed.get("patent_number")
        dedupe = make_dedupe_key(app_no, event_type, patent_no)

        assignees = list(parsed.get("assignees") or [])
        ticker = (preferred_ticker or "").upper()
        company = preferred_company or ""
        assignee_name = assignees[0] if assignees else company
        if not ticker:
            for name in assignees:
                hit = self.assignee_map.resolve(name)
                if hit:
                    ticker = hit.ticker
                    company = hit.company_name
                    assignee_name = name
                    break
        if not ticker:
            logger.debug("Skip patent app=%s — no assignee→ticker match", app_no)
            return 0

        actionable, reason = _classify_actionable(event_type, parsed.get("status_label"))

        with self.session_factory() as session:
            existing = session.exec(
                select(PatentEvent).where(PatentEvent.dedupe_key == dedupe)
            ).first()
            if existing is not None:
                return 0
            event = PatentEvent(
                dedupe_key=dedupe,
                application_number=app_no,
                patent_number=patent_no,
                event_type=event_type,
                title=str(parsed.get("title") or "")[:1024],
                assignee=assignee_name[:512],
                ticker=ticker,
                status_label=(parsed.get("status_label") or None),
                event_at=parsed.get("event_at"),
                uspto_url=str(parsed.get("uspto_url") or ""),
                google_patents_url=parsed.get("google_patents_url"),
                actionable=actionable,
                reason=reason,
                raw_json=json.dumps(parsed.get("raw") or raw, default=str)[:50_000],
            )
            session.add(event)
            session.commit()
        return 1


def _classify_actionable(event_type: str, status_label: object) -> tuple[bool, str]:
    """v1 rules: grants are actionable; new apps + most status flips are quiet."""
    if event_type == "grant":
        return True, "Patent grant matched watched assignee"
    if event_type == "application_published":
        return False, "New application published — informational"
    status = str(status_label or "").lower()
    if "allow" in status:
        return True, "Notice of allowance / allowed status"
    if "abandon" in status:
        return False, "Abandoned / status change — not alerted"
    return False, "Status change — informational"
