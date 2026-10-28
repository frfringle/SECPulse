"""Poll SEC current Atom feed and persist new filings."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from backend.config import ATOM_FEED_URL, Settings
from backend.models import Filing, Form4TransactionRow
from backend.sec.atom import ParsedFiling, parse_atom_feed
from backend.sec.client import SecClient
from backend.sec.form4 import parse_form4_xml
from backend.sec.form4_fetch import fetch_form4_xml
from backend.sec.processor import FilingProcessor, form4_has_alert
from backend.sec.ticker_cache import TickerCache

logger = logging.getLogger(__name__)


class FilingPoller:
    """Fetch Atom feed, filter/map, insert filings, enqueue Stage 3 work."""

    def __init__(
        self,
        settings: Settings,
        client: SecClient,
        ticker_cache: TickerCache,
        session_factory,
        processor: Optional[FilingProcessor] = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.ticker_cache = ticker_cache
        self.session_factory = session_factory
        self.processor = processor or FilingProcessor(
            settings, client, session_factory
        )

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

        # Process queued 8-K / 13D / Form 4 jobs (high priority first)
        try:
            processed = self.processor.process_available()
            if processed:
                logger.info("Processed %s queued filing job(s)", processed)
        except Exception as exc:  # noqa: BLE001
            logger.error("Queue processing error: %s", exc)

        logger.info(
            "Atom poll complete parsed=%s inserted=%s queue_remaining=%s",
            len(parsed),
            inserted,
            len(self.processor.queue),
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
            form4_parsed=None,
            content_parsed=None,
        )
        session.add(filing)
        session.flush()  # assign filing.id

        form4_alert = False
        if item.form_type == "4":
            self._parse_and_store_form4(session, filing)
            form4_alert = form4_has_alert(session, filing.id or 0)

        # Enqueue for Stage 3 processing (Form 4 alert / 8-K / SC 13D)
        if item.form_type in {"4", "8-K", "8-K/A", "SC 13D", "SC 13D/A"}:
            # Only queue Form 4 when it has an open-market buy alert path,
            # or always queue 8-K / 13D.
            if item.form_type != "4" or form4_alert:
                self.processor.enqueue_filing(filing, form4_alert=form4_alert)

        logger.info(
            "Stored filing accession=%s form=%s ticker=%s company=%s",
            filing.accession_number,
            filing.form_type,
            filing.ticker,
            filing.company_name,
        )
        return True

    def _parse_and_store_form4(self, session: Session, filing: Filing) -> None:
        """Fetch + parse Form 4 XML; persist transactions. Failures are non-fatal."""
        try:
            xml_text = fetch_form4_xml(self.client, filing.filing_url)
            if not xml_text:
                filing.form4_parsed = False
                logger.warning(
                    "Form 4 XML unavailable accession=%s",
                    filing.accession_number,
                )
                return

            result = parse_form4_xml(xml_text)
            alert_count = 0
            for txn in result.transactions:
                row = Form4TransactionRow(
                    filing_id=filing.id,  # type: ignore[arg-type]
                    accession_number=filing.accession_number,
                    ticker=filing.ticker or result.issuer_ticker,
                    insider_name=result.insider.name,
                    insider_role=result.insider.role,
                    is_officer=result.insider.is_officer,
                    is_director=result.insider.is_director,
                    transaction_code=txn.transaction_code,
                    shares=txn.shares,
                    price=txn.price,
                    total_value=txn.total_value,
                    acquired_disposed=txn.acquired_disposed,
                    security_title=txn.security_title,
                    transaction_date=txn.transaction_date,
                    is_10b5_1=txn.is_10b5_1,
                    alert_by_rule=txn.alert_by_rule,
                    skip_reason=txn.skip_reason,
                )
                session.add(row)
                if txn.alert_by_rule:
                    alert_count += 1

            filing.form4_parsed = True
            logger.info(
                "Form 4 parsed accession=%s insider=%s txns=%s alert_by_rule=%s",
                filing.accession_number,
                result.insider.name,
                len(result.transactions),
                alert_count,
            )
        except Exception as exc:  # noqa: BLE001 — keep ingestion resilient
            filing.form4_parsed = False
            logger.error(
                "Form 4 parse failed accession=%s error=%s",
                filing.accession_number,
                exc,
            )
