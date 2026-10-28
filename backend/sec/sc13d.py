"""Extract filer, stake %, and Item 4 from SC 13D / SC 13D/A documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from backend.sec.textutil import html_to_text, truncate_to_token_budget

_FILER_PATTERNS = [
    re.compile(
        r"(?is)Name(?:s)?\s+of\s+Reporting\s+Person(?:s)?\s*[:.\n]+\s*(?P<name>[^\n\r]{2,120})"
    ),
    re.compile(
        r"(?is)NAME\s+OF\s+REPORTING\s+PERSON(?:S)?\s*[:.\n]+\s*(?P<name>[^\n\r]{2,120})"
    ),
    re.compile(
        r"(?is)Name\s+of\s+Person\s+Filing\s*[:.\n]+\s*(?P<name>[^\n\r]{2,120})"
    ),
]

_STAKE_PATTERNS = [
    re.compile(
        r"(?is)Percent\s+of\s+Class\s+Represented(?:\s+by\s+Amount\s+in\s+Row\s*\(?11\)?)?"
        r"\s*[:.\n]+\s*(?P<pct>\d{1,3}(?:\.\d+)?)\s*%?"
    ),
    re.compile(
        r"(?is)(?:Aggregate\s+amount|beneficially\s+owned)[^\n]{0,80}?"
        r"(?P<pct>\d{1,3}(?:\.\d+)?)\s*%\s+of\s+(?:the\s+)?(?:class|outstanding)"
    ),
    re.compile(
        r"(?is)(?:owns?|ownership\s+of)\s+(?P<pct>\d{1,3}(?:\.\d+)?)\s*%\s+of"
    ),
]

_ITEM4_RE = re.compile(
    r"(?is)Item\s*4[.\s:-]*\s*(?:Purpose\s+of\s+Transaction)?\s*"
    r"(?P<body>.*?)"
    r"(?=Item\s*5\b|SIGNATURES\b|Item\s*6\b|\Z)",
)


@dataclass
class SC13DParseResult:
    filer_name: str
    stake_percent: Optional[float]
    item4_text: str
    combined_text: str
    truncated: bool = False


def _first_match(patterns: list[re.Pattern[str]], text: str, group: str) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(group).strip()
    return ""


def extract_filer(text: str) -> str:
    name = _first_match(_FILER_PATTERNS, text, "name")
    # Drop trailing form noise
    name = re.split(r"\s{2,}|\t|Check\b|I\.R\.S\b", name, maxsplit=1)[0].strip(" .")
    return name


def extract_stake_percent(text: str) -> Optional[float]:
    raw = _first_match(_STAKE_PATTERNS, text, "pct")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def extract_item4(text: str) -> str:
    match = _ITEM4_RE.search(text)
    if not match:
        return ""
    body = match.group("body").strip()
    # Remove a duplicated heading remnant
    body = re.sub(
        r"(?i)^Purpose\s+of\s+Transaction\.?\s*",
        "",
        body,
    ).strip()
    return body


def parse_sc13d(document: str, *, token_budget: int = 4000) -> SC13DParseResult:
    text = html_to_text(document)
    filer = extract_filer(text)
    stake = extract_stake_percent(text)
    item4 = extract_item4(text)

    parts = [
        f"Filer: {filer or 'Unknown'}",
        f"Stake %: {stake if stake is not None else 'Unknown'}",
        f"Item 4 — Purpose of Transaction:\n{item4}" if item4 else "Item 4: (not found)",
    ]
    combined = "\n\n".join(parts)
    combined, truncated = truncate_to_token_budget(combined, token_budget)

    return SC13DParseResult(
        filer_name=filer,
        stake_percent=stake,
        item4_text=item4,
        combined_text=combined,
        truncated=truncated,
    )
