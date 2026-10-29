"""Pydantic schema for Ollama JSON scoring output."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Direction = Literal["bullish", "bearish", "neutral"]


class ScoringResult(BaseModel):
    """Strict score payload returned by the local Ollama model."""

    direction: Direction
    confidence: int = Field(ge=0, le=100)
    summary: str
    key_evidence: str
    event_type: str

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_direction(cls, value: Any) -> str:
        if value is None:
            raise ValueError("direction is required")
        text = str(value).strip().lower()
        if text not in {"bullish", "bearish", "neutral"}:
            raise ValueError(f"invalid direction: {value!r}")
        return text

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, value: Any) -> int:
        if isinstance(value, str):
            value = value.strip().rstrip("%")
        conf = int(float(value))
        if conf < 0 or conf > 100:
            raise ValueError("confidence must be 0-100")
        return conf

    @field_validator("summary")
    @classmethod
    def limit_summary(cls, value: str) -> str:
        text = " ".join(value.split()).strip()
        if not text:
            raise ValueError("summary must be non-empty")
        # Soft cap: keep <= ~2 sentences by truncating excess sentences
        parts = re.split(r"(?<=[.!?])\s+", text)
        if len(parts) > 2:
            text = " ".join(parts[:2]).strip()
        return text

    @field_validator("key_evidence", "event_type")
    @classmethod
    def non_empty(cls, value: str) -> str:
        text = " ".join(str(value).split()).strip()
        if not text:
            raise ValueError("field must be non-empty")
        return text

    @model_validator(mode="after")
    def routine_should_be_neutral_hint(self) -> ScoringResult:
        # No hard reject — prompt instructs neutral for routine; validation stays schema-only.
        return self

    def should_alert(self, threshold: int) -> bool:
        return self.direction != "neutral" and self.confidence >= threshold


def parse_scoring_json(raw: str) -> ScoringResult:
    """Parse model text into ScoringResult; raises ValidationError/JSONDecodeError."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty model output")
    # Tolerate accidental markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("model output must be a JSON object")
    return ScoringResult.model_validate(data)
