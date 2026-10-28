"""Priority-queue driven processing for Form 4 / 8-K / SC 13D content."""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlmodel import Session, select

from backend.config import Settings
from backend.models import EightKExtraction, Filing, Form4TransactionRow, SC13DExtraction
from backend.sec.client import SecClient
from backend.sec.docs import fetch_filing_documents
from backend.sec.eightk import parse_eightk
from backend.sec.priority import (
    JobPriority,
    PriorityQueue,
    ProcessJob,
    priority_for_form,
)
from backend.sec.sc13d import parse_sc13d

logger = logging.getLogger(__name__)


class FilingProcessor:
    """Enqueue and process filings in priority order."""

    def __init__(
        self,
        settings: Settings,
        client: SecClient,
        session_factory,
        queue: Optional[PriorityQueue] = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.session_factory = session_factory
        self.queue = queue or PriorityQueue()

    def enqueue_filing(
        self,
        filing: Filing,
        *,
        form4_alert: bool = False,
        eightk_items: Optional[set[str]] = None,
    ) -> ProcessJob:
        priority, reason = priority_for_form(
            filing.form_type,
            form4_alert=form4_alert,
            eightk_items=eightk_items,
        )
        job = ProcessJob(
            filing_id=filing.id or 0,
            accession_number=filing.accession_number,
            form_type=filing.form_type,
            ticker=filing.ticker,
            filing_url=filing.filing_url,
            priority=priority,
            reason=reason,
            high_priority_items=tuple(sorted(eightk_items or ())),
            form4_alert=form4_alert,
        )
        self.queue.push(job)
        filing.queue_priority = int(priority)
        filing.queue_reason = reason
        return job

    def process_available(self, max_jobs: Optional[int] = None) -> int:
        """Drain (or partially drain) the queue. Returns jobs processed."""
        processed = 0
        while max_jobs is None or processed < max_jobs:
            job = self.queue.pop()
            if job is None:
                break
            try:
                self._process_job(job)
                processed += 1
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Processing failed accession=%s form=%s error=%s",
                    job.accession_number,
                    job.form_type,
                    exc,
                )
                with self.session_factory() as session:
                    filing = session.get(Filing, job.filing_id)
                    if filing is not None:
                        filing.content_parsed = False
                        session.add(filing)
                        session.commit()
        return processed

    def _process_job(self, job: ProcessJob) -> None:
        if job.form_type == "4":
            # Form 4 XML already parsed in Stage 2; queue entry is for later scoring
            with self.session_factory() as session:
                filing = session.get(Filing, job.filing_id)
                if filing is not None:
                    filing.content_parsed = True
                    session.add(filing)
                    session.commit()
            logger.info(
                "Form 4 job acknowledged accession=%s alert=%s",
                job.accession_number,
                job.form4_alert,
            )
            return

        if job.form_type in {"8-K", "8-K/A"}:
            self._process_eightk(job)
            return

        if job.form_type in {"SC 13D", "SC 13D/A"}:
            self._process_sc13d(job)
            return

        logger.debug("No Stage 3 handler for form=%s", job.form_type)

    def _process_eightk(self, job: ProcessJob) -> None:
        docs = fetch_filing_documents(
            self.client, job.filing_url, form_family="8k"
        )
        if not docs.primary_text:
            raise RuntimeError(f"No 8-K primary document for {job.accession_number}")

        parsed = parse_eightk(
            docs.primary_text,
            exhibit_99_1_html=docs.exhibit_99_1_text or None,
            exhibit_99_1_listed=docs.exhibit_99_1_listed,
            token_budget=self.settings.token_budget,
        )

        # Re-rank if we discovered high-priority items after fetch
        if parsed.has_high_priority and job.priority < JobPriority.EIGHT_K_HIGH:
            job.priority = JobPriority.EIGHT_K_HIGH
            job.reason = f"eightk_high:{','.join(parsed.high_priority_item_numbers)}"

        items_payload = [
            {
                "number": i.number,
                "title": i.title,
                "text": i.text,
                "is_high_priority": i.is_high_priority,
            }
            for i in parsed.items
        ]

        with self.session_factory() as session:
            filing = session.get(Filing, job.filing_id)
            row = EightKExtraction(
                filing_id=job.filing_id,
                accession_number=job.accession_number,
                ticker=job.ticker,
                item_numbers=",".join(i.number for i in parsed.items),
                high_priority_items=",".join(parsed.high_priority_item_numbers),
                has_exhibit_99_1=parsed.has_exhibit_99_1,
                no_press_release=parsed.no_press_release,
                items_json=json.dumps(items_payload),
                combined_text=parsed.combined_text,
                truncated=parsed.truncated,
            )
            session.add(row)
            if filing is not None:
                filing.content_parsed = True
                filing.queue_priority = int(job.priority)
                filing.queue_reason = job.reason
                session.add(filing)
            session.commit()

        logger.info(
            "8-K extracted accession=%s items=%s high=%s no_press_release=%s truncated=%s",
            job.accession_number,
            [i.number for i in parsed.items],
            parsed.high_priority_item_numbers,
            parsed.no_press_release,
            parsed.truncated,
        )

    def _process_sc13d(self, job: ProcessJob) -> None:
        docs = fetch_filing_documents(
            self.client, job.filing_url, form_family="13d"
        )
        if not docs.primary_text:
            raise RuntimeError(f"No SC 13D primary document for {job.accession_number}")

        parsed = parse_sc13d(
            docs.primary_text, token_budget=self.settings.token_budget
        )

        with self.session_factory() as session:
            filing = session.get(Filing, job.filing_id)
            row = SC13DExtraction(
                filing_id=job.filing_id,
                accession_number=job.accession_number,
                ticker=job.ticker,
                filer_name=parsed.filer_name,
                stake_percent=parsed.stake_percent,
                item4_text=parsed.item4_text,
                combined_text=parsed.combined_text,
                truncated=parsed.truncated,
            )
            session.add(row)
            if filing is not None:
                filing.content_parsed = True
                filing.queue_priority = int(JobPriority.SC13D)
                filing.queue_reason = "sc13d"
                session.add(filing)
            session.commit()

        logger.info(
            "SC 13D extracted accession=%s filer=%s stake=%s truncated=%s",
            job.accession_number,
            parsed.filer_name,
            parsed.stake_percent,
            parsed.truncated,
        )


def form4_has_alert(session: Session, filing_id: int) -> bool:
    row = session.exec(
        select(Form4TransactionRow).where(
            Form4TransactionRow.filing_id == filing_id,
            Form4TransactionRow.alert_by_rule == True,  # noqa: E712
        )
    ).first()
    return row is not None
