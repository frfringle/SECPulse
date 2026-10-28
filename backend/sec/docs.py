"""Fetch primary documents and exhibits from an EDGAR filing index."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin

from backend.sec.client import SecClient
from backend.sec.form4_fetch import filing_directory_url

logger = logging.getLogger(__name__)


@dataclass
class IndexDocument:
    href: str
    description: str = ""
    form_type: str = ""


@dataclass
class FilingDocuments:
    primary_url: Optional[str] = None
    primary_text: str = ""
    exhibit_99_1_url: Optional[str] = None
    exhibit_99_1_text: str = ""
    exhibit_99_1_listed: bool = False
    all_docs: list[IndexDocument] = field(default_factory=list)


class _IndexTableParser(HTMLParser):
    """Collect document links + nearby text from an EDGAR index.htm."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[IndexDocument] = []
        self._in_a = False
        self._current_href: Optional[str] = None
        self._current_text: list[str] = []
        self._row_text: list[str] = []
        self._in_tr = False

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t == "tr":
            self._in_tr = True
            self._row_text = []
        if t == "a":
            href = dict(attrs).get("href")
            if href:
                self._in_a = True
                self._current_href = href
                self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "a" and self._in_a and self._current_href:
            desc = "".join(self._current_text).strip()
            self.rows.append(
                IndexDocument(href=self._current_href, description=desc)
            )
            self._in_a = False
            self._current_href = None
        if t == "tr" and self._in_tr:
            row_blob = " ".join(self._row_text)
            if self.rows and not self.rows[-1].form_type:
                # Capture type column hints like 8-K, EX-99.1
                type_match = re.search(
                    r"\b(8-K(?:/A)?|SC\s*13D(?:/A)?|EX-99\.1|EX-99\.1)\b",
                    row_blob,
                    re.I,
                )
                if type_match:
                    self.rows[-1].form_type = type_match.group(1).upper().replace(
                        "SC13D", "SC 13D"
                    )
            self._in_tr = False

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._current_text.append(data)
        if self._in_tr:
            self._row_text.append(data)


def parse_index_documents(html: str) -> list[IndexDocument]:
    parser = _IndexTableParser()
    parser.feed(html)
    return parser.rows


def _is_primary_candidate(doc: IndexDocument, form_family: str) -> bool:
    href = doc.href.lower()
    desc = f"{doc.description} {doc.form_type}".lower()
    if href.endswith(".xml") and "xsl" in href:
        return False
    if form_family == "8k":
        if re.search(r"ex[-_]?99|exhibit", href) or "ex-99" in desc:
            return False
        if href.endswith((".htm", ".html", ".txt")):
            if re.search(r"8[-_]?k|form8k|f8k", href) or "8-k" in desc:
                return True
            # Generic primary often named like d123.htm
            if not re.search(r"ex[-_]?\d", href):
                return True
    if form_family == "13d":
        if href.endswith((".htm", ".html", ".txt", ".xml")):
            if re.search(r"13d|sc13d|schedule", href) or "13d" in desc:
                return True
            if not re.search(r"ex[-_]?\d", href):
                return True
    return False


def pick_primary_url(
    docs: list[IndexDocument], base_url: str, form_family: str
) -> Optional[str]:
    for doc in docs:
        if _is_primary_candidate(doc, form_family):
            return urljoin(base_url, doc.href)
    # Fallback: first htm/html
    for doc in docs:
        lower = doc.href.lower()
        if lower.endswith((".htm", ".html", ".txt")) and "xsl" not in lower:
            return urljoin(base_url, doc.href)
    return None


def pick_exhibit_99_1(
    docs: list[IndexDocument], base_url: str
) -> tuple[Optional[str], bool]:
    listed = False
    for doc in docs:
        blob = f"{doc.href} {doc.description} {doc.form_type}"
        if re.search(r"ex-?99\.?1\b|exhibit\s*99\.1", blob, re.I):
            listed = True
            lower = doc.href.lower()
            if lower.endswith((".htm", ".html", ".txt")):
                return urljoin(base_url, doc.href), True
    return None, listed


def fetch_filing_documents(
    client: SecClient,
    filing_url: str,
    *,
    form_family: str,
) -> FilingDocuments:
    """Download primary (+ Exhibit 99.1 for 8-K) for a filing index URL."""
    result = FilingDocuments()
    directory = filing_directory_url(filing_url)
    if directory is None:
        logger.warning("Bad filing url for docs fetch: %s", filing_url)
        return result

    try:
        index_html = client.get(filing_url).text
    except Exception as exc:  # noqa: BLE001
        logger.error("Index fetch failed url=%s error=%s", filing_url, exc)
        return result

    docs = parse_index_documents(index_html)
    result.all_docs = docs
    primary = pick_primary_url(docs, directory, form_family)
    result.primary_url = primary
    if primary:
        try:
            result.primary_text = client.get(primary).text
        except Exception as exc:  # noqa: BLE001
            logger.error("Primary doc fetch failed url=%s error=%s", primary, exc)

    if form_family == "8k":
        ex_url, listed = pick_exhibit_99_1(docs, directory)
        result.exhibit_99_1_listed = listed or ex_url is not None
        result.exhibit_99_1_url = ex_url
        if ex_url:
            try:
                result.exhibit_99_1_text = client.get(ex_url).text
            except Exception as exc:  # noqa: BLE001
                logger.error("Exhibit 99.1 fetch failed url=%s error=%s", ex_url, exc)

    return result
