"""Priority-queue driven processing for Form 4 / 8-K / SC 13D + Ollama scoring."""

from __future__ import annotations

import json
import logging
from typing import Optional

from sqlmodel import Session, select

from backend.config import Settings
from backend.models import (
    EightKExtraction,
    Filing,
    Form4TransactionRow,
    SC13DExtraction,
    ScoringQueueItem,
)
from backend.scoring.alerts import (
    create_alert,
    enqueue_scoring_retry,
    list_pending_scoring,
    mark_queue_done,
)
from backend.scoring.ollama import OllamaClient
from backend.scoring.scorer import FilingScorer, form4_rule_score
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
    """Enqueue and process filings in priority order; score with Ollama."""

    def __init__(
        self,
        settings: Settings,
        client: SecClient,
        session_factory,
        queue: Optional[PriorityQueue] = None,
        scorer: Optional[FilingScorer] = None,
        ollama_client: Optional[OllamaClient] = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.session_factory = session_factory
        self.queue = queue or PriorityQueue()
        if scorer is not None:
            self.scorer = scorer
        else:
            ollama = ollama_client or OllamaClient(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
            self.scorer = FilingScorer(
                ollama, alert_threshold=settings.alert_threshold
            )

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
        """Drain the in-memory queue, then retry durable Ollama scoring queue."""
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

        # Never drop: retry filings waiting on Ollama
        retried = self.process_scoring_retries(
            max_jobs=None if max_jobs is None else max(0, max_jobs - processed)
        )
        return processed + retried

    def process_scoring_retries(self, max_jobs: Optional[int] = None) -> int:
        done = 0
        with self.session_factory() as session:
            pending = list_pending_scoring(session, limit=max_jobs or 50)
            # Detach ids before leaving nested transaction patterns
            items = [
                (
                    item.id,
                    item.filing_id,
                    item.filing_text,
                    item.form_type,
                    item.ticker,
                    item.company_name,
                    item.priority,
                )
                for item in pending
            ]

        for (
            item_id,
            filing_id,
            filing_text,
            form_type,
            ticker,
            company_name,
            _priority,
        ) in items:
            if max_jobs is not None and done >= max_jobs:
                break
            outcome = self.scorer.score_filing_text(
                form_type=form_type,
                ticker=ticker,
                company_name=company_name,
                filing_text=filing_text,
            )
            with self.session_factory() as session:
                item = session.get(ScoringQueueItem, item_id)
                filing = session.get(Filing, filing_id)
                if item is None or filing is None:
                    continue

                if not outcome.ok or outcome.result is None:
                    err = outcome.error or "unknown"
                    item.attempts += 1
                    item.last_error = err[:512]
                    filing.score_status = "awaiting_ollama"
                    filing.score_attempts = item.attempts
                    filing.last_score_error = err[:512]
                    session.add(item)
                    session.add(filing)
                    session.commit()
                    logger.warning(
                        "Scoring retry still pending accession=%s error=%s",
                        filing.accession_number,
                        err,
                    )
                    continue

                self._apply_score(session, filing, outcome.result, source="ollama")
                mark_queue_done(session, item)
                session.commit()
                done += 1
        return done

    def _process_job(self, job: ProcessJob) -> None:
        if job.form_type == "4":
            self._process_form4_alert(job)
            return

        if job.form_type in {"8-K", "8-K/A"}:
            self._process_eightk(job)
            return

        if job.form_type in {"SC 13D", "SC 13D/A"}:
            self._process_sc13d(job)
            return

        logger.debug("No Stage 3/4 handler for form=%s", job.form_type)

    def _process_form4_alert(self, job: ProcessJob) -> None:
        """Form 4 open-market buys alert by rule — no Ollama required."""
        with self.session_factory() as session:
            filing = session.get(Filing, job.filing_id)
            if filing is None:
                return
            filing.content_parsed = True
            if not job.form4_alert:
                filing.score_status = "scored"
                session.add(filing)
                session.commit()
                return

            txn = session.exec(
                select(Form4TransactionRow).where(
                    Form4TransactionRow.filing_id == filing.id,
                    Form4TransactionRow.alert_by_rule == True,  # noqa: E712
                )
            ).first()
            if txn is None:
                filing.score_status = "scored"
                session.add(filing)
                session.commit()
                return

            result = form4_rule_score(
                insider_name=txn.insider_name,
                insider_role=txn.insider_role,
                shares=txn.shares,
                price=txn.price,
                total_value=txn.total_value,
            )
            create_alert(session, filing=filing, result=result, source="form4_rule")
            filing.score_status = "alerted"
            session.add(filing)
            session.commit()
            logger.info(
                "Form 4 rule alert accession=%s ticker=%s insider=%s",
                filing.accession_number,
                filing.ticker,
                txn.insider_name,
            )

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
            company = filing.company_name if filing else ""

        logger.info(
            "8-K extracted accession=%s items=%s high=%s no_press_release=%s truncated=%s",
            job.accession_number,
            [i.number for i in parsed.items],
            parsed.high_priority_item_numbers,
            parsed.no_press_release,
            parsed.truncated,
        )

        self._score_and_maybe_alert(
            filing_id=job.filing_id,
            form_type=job.form_type,
            ticker=job.ticker,
            company_name=company,
            filing_text=parsed.combined_text,
            priority=int(job.priority),
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
            company = ""
            if filing is not None:
                filing.content_parsed = True
                filing.queue_priority = int(JobPriority.SC13D)
                filing.queue_reason = "sc13d"
                session.add(filing)
                company = filing.company_name
            session.commit()

        logger.info(
            "SC 13D extracted accession=%s filer=%s stake=%s truncated=%s",
            job.accession_number,
            parsed.filer_name,
            parsed.stake_percent,
            parsed.truncated,
        )

        self._score_and_maybe_alert(
            filing_id=job.filing_id,
            form_type=job.form_type,
            ticker=job.ticker,
            company_name=company,
            filing_text=parsed.combined_text,
            priority=int(JobPriority.SC13D),
        )

    def _score_and_maybe_alert(
        self,
        *,
        filing_id: int,
        form_type: str,
        ticker: str,
        company_name: str,
        filing_text: str,
        priority: int,
    ) -> None:
        outcome = self.scorer.score_filing_text(
            form_type=form_type,
            ticker=ticker,
            company_name=company_name,
            filing_text=filing_text,
        )
        with self.session_factory() as session:
            filing = session.get(Filing, filing_id)
            if filing is None:
                return

            if not outcome.ok or outcome.result is None:
                err = outcome.error or "unknown"
                enqueue_scoring_retry(
                    session,
                    filing=filing,
                    filing_text=filing_text,
                    priority=priority,
                    error=err,
                )
                session.commit()
                logger.warning(
                    "Queued scoring retry accession=%s error=%s",
                    filing.accession_number,
                    err,
                )
                return

            self._apply_score(session, filing, outcome.result, source="ollama")
            session.commit()

    def _apply_score(self, session: Session, filing: Filing, result, source: str) -> None:
        if self.scorer.should_alert(result):
            create_alert(session, filing=filing, result=result, source=source)
            filing.score_status = "alerted"
            logger.info(
                "Alert created accession=%s ticker=%s direction=%s confidence=%s source=%s",
                filing.accession_number,
                filing.ticker,
                result.direction,
                result.confidence,
                source,
            )
        else:
            filing.score_status = "scored"
            logger.info(
                "Scored (no alert) accession=%s direction=%s confidence=%s",
                filing.accession_number,
                result.direction,
                result.confidence,
            )
        filing.last_score_error = None
        filing.score_attempts = (filing.score_attempts or 0) + 1
        session.add(filing)


def form4_has_alert(session: Session, filing_id: int) -> bool:
    row = session.exec(
        select(Form4TransactionRow).where(
            Form4TransactionRow.filing_id == filing_id,
            Form4TransactionRow.alert_by_rule == True,  # noqa: E712
        )
    ).first()
    return row is not None
