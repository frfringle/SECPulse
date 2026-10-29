"""Extract Item sections and Exhibit 99.1 from Form 8-K HTML/text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from backend.sec.priority import HIGH_PRIORITY_8K_ITEMS
from backend.sec.textutil import html_to_text, truncate_to_token_budget

# Match "Item 1.01" / "ITEM 2.02" headings; require a following title-ish char
# to avoid body references when possible (title often follows on same line).
_ITEM_HEADING_RE = re.compile(
    r"(?m)^\s*Item\s+(?P<num>\d+\.\d{2})\b[^\n]*",
    re.IGNORECASE,
)

_EX99_RE = re.compile(
    r"EX-?99\.?1\b|Exhibit\s+99\.1\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EightKItem:
    number: str  # e.g. "1.01"
    title: str
    text: str
    is_high_priority: bool


@dataclass
class EightKParseResult:
    items: list[EightKItem] = field(default_factory=list)
    has_exhibit_99_1: bool = False
    no_press_release: bool = True
    exhibit_99_1_text: str = ""
    combined_text: str = ""
    truncated: bool = False
    high_priority_item_numbers: list[str] = field(default_factory=list)

    @property
    def has_high_priority(self) -> bool:
        return bool(self.high_priority_item_numbers)


def _split_heading(match: re.Match[str]) -> tuple[str, str]:
    number = match.group("num")
    # Remainder of the heading line after "Item X.XX"
    full = match.group(0)
    after = re.sub(
        rf"^\s*Item\s+{re.escape(number)}\b[.\s:-]*",
        "",
        full,
        flags=re.IGNORECASE,
    ).strip(" .\t")
    return number, after


def extract_eightk_items(document_text: str) -> list[EightKItem]:
    """Parse Item N.NN sections from an 8-K primary document (HTML or text)."""
    text = html_to_text(document_text)
    matches = list(_ITEM_HEADING_RE.finditer(text))
    if not matches:
        return []

    items: list[EightKItem] = []
    for i, match in enumerate(matches):
        number, title = _split_heading(match)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # Stop at signatures / exhibits table noise if present mid-doc
        body = re.split(
            r"(?i)\n\s*(?:SIGNATURES|EXHIBIT\s+INDEX)\b",
            body,
            maxsplit=1,
        )[0].strip()
        items.append(
            EightKItem(
                number=number,
                title=title,
                text=body,
                is_high_priority=number in HIGH_PRIORITY_8K_ITEMS,
            )
        )
    return items


def parse_eightk(
    primary_html: str,
    *,
    exhibit_99_1_html: Optional[str] = None,
    exhibit_99_1_listed: bool = False,
    token_budget: int = 4000,
) -> EightKParseResult:
    """Full 8-K parse: items + optional Exhibit 99.1 + token truncation."""
    items = extract_eightk_items(primary_html)
    has_ex99 = bool(exhibit_99_1_html) or exhibit_99_1_listed
    if not has_ex99:
        # Some primaries embed a mention without a separate file
        has_ex99 = bool(_EX99_RE.search(primary_html or ""))

    ex_text = html_to_text(exhibit_99_1_html) if exhibit_99_1_html else ""
    no_press_release = not has_ex99 and not ex_text

    parts: list[str] = []
    high_nums: list[str] = []
    for item in items:
        if item.is_high_priority:
            high_nums.append(item.number)
        header = f"Item {item.number}"
        if item.title:
            header += f" — {item.title}"
        parts.append(f"{header}\n{item.text}".strip())

    if ex_text:
        parts.append(f"Exhibit 99.1\n{ex_text}")
    elif no_press_release:
        parts.append("FLAG: no press release (Exhibit 99.1 not present)")

    combined = "\n\n".join(parts)
    combined, truncated = truncate_to_token_budget(combined, token_budget)

    return EightKParseResult(
        items=items,
        has_exhibit_99_1=has_ex99,
        no_press_release=no_press_release,
        exhibit_99_1_text=ex_text,
        combined_text=combined,
        truncated=truncated,
        high_priority_item_numbers=high_nums,
    )
