"""Poll SEC current Atom feed and persist new filings."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlmodel import Session, select

from backend.config import ATOM_FEED_URL, Settings
from backend.models import Filing
from backend.sec.atom import ParsedFiling, parse_atom_feed
from backend.sec.client import SecClient
from backend.sec.ticker_cache import TickerCache

logger = logging.getLogger(__name__)


class FilingPoller:
    """Fetch Atom feed, filter/map, and insert unseen filings."""

    def __init__(
        self,
        settings: Settings,
        client: SecClient,
        ticker_cache: TickerCache,
        session_factory,
    ) -> None:
        self.settings = settings
        self.client = client
        self.ticker_cache = ticker_cache
        self.session_factory = session_factory

    def poll_once(self) -> int:
        """Run one poll cycle. Returns number of newly stored filings."""
        try:
            response = self.client.get(ATOM_FEED_URL)
            xml_text = response.text
        except Exception as exc:  # noqa: BLE001 — graceful SEC failure
            logger.error("Atom poll failed (will retry next interval): %s", exc)
            return 0

        try:
            parsed = parse_atom_feed(xml_text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Atom parse failed: %s", exc)
            return 0

        self.ticker_cache.load()
        inserted = 0

        with self.session_factory() as session:
            for item in parsed:
                if self._store_if_new(session, item):
                    inserted += 1
            session.commit()

        logger.info(
            "Atom poll complete parsed=%s inserted=%s",
            len(parsed),
            inserted,
        )
        return inserted

    def _store_if_new(self, session: Session, item: ParsedFiling) -> bool:
        existing = session.exec(
            select(Filing).where(Filing.accession_number == item.accession_number)
        ).first()
        if existing is not None:
            return False

        ticker = self.ticker_cache.lookup(item.cik)
        if not ticker:
            logger.debug(
                "Skipping filing without ticker accession=%s cik=%s form=%s",
                item.accession_number,
                item.cik,
                item.form_type,
            )
            return False

        accepted = item.accepted_at
        if accepted.tzinfo is None:
            accepted = accepted.replace(tzinfo=timezone.utc)
        else:
            accepted = accepted.astimezone(timezone.utc)

        filing = Filing(
            accession_number=item.accession_number,
            form_type=item.form_type,
            cik=item.cik,
            company_name=item.company_name,
            ticker=ticker,
            accepted_at=accepted,
            filing_url=item.filing_url,
            ingested_at=datetime.now(timezone.utc),
        )
        session.add(filing)
        logger.info(
            "Stored filing accession=%s form=%s ticker=%s company=%s",
            filing.accession_number,
            filing.form_type,
            filing.ticker,
            filing.company_name,
        )
        return True
