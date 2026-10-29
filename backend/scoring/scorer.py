"""Score filings with Ollama; validate JSON; retry once; decide alerts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from pydantic import ValidationError

from backend.scoring.ollama import OllamaClient, OllamaError
from backend.scoring.schema import ScoringResult, parse_scoring_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a filing analyst for short-term stock price reaction \
(same day to a few trading days). Read the SEC filing excerpt and judge whether \
the market is likely to react bullishly, bearishly, or not at all.

Rules:
- Answer "neutral" for routine, administrative, or expected filings with little \
new price-moving information (e.g. ordinary 8-K housekeeping, boilerplate, \
immaterial updates).
- Use "bullish" or "bearish" only when the filing contains material new information \
likely to move the stock in the short term.
- confidence is an integer 0-100 reflecting how sure you are.
- summary must be at most two short sentences.
- key_evidence must be a short quote or paraphrase taken from the filing text.
- event_type is a short snake_case or kebab label (e.g. material_agreement, \
acquisition, bankruptcy, auditor_change, activist_13d, executive_departure).

Respond with JSON only matching this schema:
{
  "direction": "bullish" | "bearish" | "neutral",
  "confidence": 0-100,
  "summary": "<=2 sentences",
  "key_evidence": "short quote from filing",
  "event_type": "string"
}
"""

RETRY_HINT = (
    "Your previous reply was invalid. Return ONLY a single JSON object with keys "
    "direction, confidence, summary, key_evidence, event_type. "
    "direction must be bullish, bearish, or neutral. confidence 0-100."
)


@dataclass
class ScoreOutcome:
    result: Optional[ScoringResult]
    raw_responses: list[str]
    error: Optional[str] = None
    retried: bool = False

    @property
    def ok(self) -> bool:
        return self.result is not None and self.error is None


class FilingScorer:
    """Call Ollama, validate with Pydantic, retry once on bad JSON/schema."""

    def __init__(self, client: OllamaClient, alert_threshold: int = 65) -> None:
        self.client = client
        self.alert_threshold = alert_threshold

    def score_filing_text(
        self,
        *,
        form_type: str,
        ticker: str,
        company_name: str,
        filing_text: str,
    ) -> ScoreOutcome:
        user = (
            f"Form: {form_type}\n"
            f"Ticker: {ticker}\n"
            f"Company: {company_name}\n\n"
            f"Filing excerpt:\n{filing_text}"
        )
        raws: list[str] = []
        try:
            raw = self.client.chat_json(system=SYSTEM_PROMPT, user=user)
            raws.append(raw)
            try:
                result = parse_scoring_json(raw)
                return ScoreOutcome(result=result, raw_responses=raws)
            except (ValidationError, ValueError, TypeError) as first_exc:
                logger.warning("Ollama JSON invalid; retrying once: %s", first_exc)
                raw2 = self.client.chat_json(
                    system=SYSTEM_PROMPT,
                    user=user + "\n\n" + RETRY_HINT,
                )
                raws.append(raw2)
                try:
                    result = parse_scoring_json(raw2)
                    return ScoreOutcome(
                        result=result, raw_responses=raws, retried=True
                    )
                except (ValidationError, ValueError, TypeError) as second_exc:
                    return ScoreOutcome(
                        result=None,
                        raw_responses=raws,
                        error=f"invalid_json_after_retry: {second_exc}",
                        retried=True,
                    )
        except OllamaError as exc:
            return ScoreOutcome(
                result=None,
                raw_responses=raws,
                error=f"ollama_unavailable: {exc}",
            )

    def should_alert(self, result: ScoringResult) -> bool:
        return result.should_alert(self.alert_threshold)


def form4_rule_score(
    *,
    insider_name: str,
    insider_role: str,
    shares: float,
    price: Optional[float],
    total_value: Optional[float],
) -> ScoringResult:
    """Deterministic score for officer/director open-market Form 4 buys."""
    price_bit = f" @ ${price:.2f}" if price is not None else ""
    value_bit = f" (≈${total_value:,.0f})" if total_value is not None else ""
    summary = (
        f"{insider_name} ({insider_role}) open-market bought "
        f"{shares:g} shares{price_bit}{value_bit}."
    )
    return ScoringResult(
        direction="bullish",
        confidence=100,
        summary=summary,
        key_evidence=f"Form 4 code P by {insider_role}: {shares:g} shares",
        event_type="form4_open_market_buy",
    )
