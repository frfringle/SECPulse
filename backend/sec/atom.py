"""Parse SEC current filings Atom feed into structured filing records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree as ET

from backend.config import WATCHED_FORMS

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Title examples:
#   "8-K - Apple Inc. (0000320193) (Filer)"
#   "4 - Tesla, Inc. (0001318605) (Reporting)"
#   "SC 13D/A - Some Company (0001234567) (Filer)"
_TITLE_RE = re.compile(
    r"^(?P<form>.+?)\s+-\s+(?P<company>.+?)\s+\((?P<cik>\d+)\)",
)

# Accession in id / link, e.g. 0000320193-24-000001
_ACCESSION_RE = re.compile(r"(\d{10}-\d{2}-\d{6})")


@dataclass(frozen=True)
class ParsedFiling:
    accession_number: str
    form_type: str
    cik: str
    company_name: str
    accepted_at: datetime
    filing_url: str


def _text(el: Optional[ET.Element]) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _parse_updated(value: str) -> datetime:
    """Parse Atom updated/published timestamps into aware UTC datetime."""
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_accession(*candidates: str) -> Optional[str]:
    for text in candidates:
        match = _ACCESSION_RE.search(text or "")
        if match:
            return match.group(1)
    return None


def _normalize_form(form: str) -> str:
    return " ".join(form.split()).upper().replace("SC13D", "SC 13D")


def parse_title(title: str) -> Optional[tuple[str, str, str]]:
    """Return (form_type, company_name, cik) from an Atom entry title, or None."""
    match = _TITLE_RE.match(title.strip())
    if not match:
        return None
    form = _normalize_form(match.group("form").strip())
    company = match.group("company").strip()
    cik = match.group("cik").zfill(10)
    return form, company, cik


def parse_atom_feed(xml_text: str) -> list[ParsedFiling]:
    """Parse Atom XML; return watched-form filings (dedupe by accession later)."""
    root = ET.fromstring(xml_text)
    filings: list[ParsedFiling] = []

    for entry in root.findall("atom:entry", ATOM_NS):
        title = _text(entry.find("atom:title", ATOM_NS))
        parsed_title = parse_title(title)
        if parsed_title is None:
            continue
        form_type, company_name, cik = parsed_title
        if form_type not in WATCHED_FORMS:
            continue

        entry_id = _text(entry.find("atom:id", ATOM_NS))
        link_el = entry.find("atom:link", ATOM_NS)
        href = link_el.get("href", "") if link_el is not None else ""
        summary = _text(entry.find("atom:summary", ATOM_NS))

        accession = _extract_accession(entry_id, href, summary, title)
        if not accession:
            continue

        updated = _text(entry.find("atom:updated", ATOM_NS)) or _text(
            entry.find("atom:published", ATOM_NS)
        )
        if not updated:
            continue
        accepted_at = _parse_updated(updated)

        filing_url = href or entry_id
        filings.append(
            ParsedFiling(
                accession_number=accession,
                form_type=form_type,
                cik=cik,
                company_name=company_name,
                accepted_at=accepted_at,
                filing_url=filing_url,
            )
        )

    return filings
