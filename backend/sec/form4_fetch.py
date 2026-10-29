"""Locate and download Form 4 ownership XML from an EDGAR filing index."""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin

from backend.sec.client import SecClient

logger = logging.getLogger(__name__)

_INDEX_RE = re.compile(
    r"(?P<base>https?://www\.sec\.gov/Archives/edgar/data/\d+/\d+)/"
    r"(?P<acc>[\d-]+)-index\.htm[l]?",
    re.IGNORECASE,
)


class _HrefCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def filing_directory_url(filing_url: str) -> Optional[str]:
    """Return the EDGAR directory URL for an index.htm filing link."""
    match = _INDEX_RE.match(filing_url.strip())
    if match:
        return match.group("base") + "/"
    # Already a directory?
    if "/Archives/edgar/data/" in filing_url and filing_url.endswith("/"):
        return filing_url
    return None


def pick_ownership_xml_href(hrefs: list[str], base_url: str) -> Optional[str]:
    """Choose the ownership Form 4 XML among document links.

    Prefers raw ownership XML over xsl-transformed HTML wrappers.
    """
    candidates: list[str] = []
    for href in hrefs:
        lower = href.lower()
        if not lower.endswith(".xml"):
            continue
        if "xslf345" in lower or "/xsl/" in lower:
            continue
        absolute = urljoin(base_url, href)
        candidates.append(absolute)

    if not candidates:
        return None

    preferred = [
        c
        for c in candidates
        if re.search(r"form4|primary_doc|ownership|wk-form4", c, re.I)
    ]
    return (preferred or candidates)[0]


def extract_xml_hrefs_from_index(html: str, base_url: str) -> Optional[str]:
    parser = _HrefCollector()
    parser.feed(html)
    return pick_ownership_xml_href(parser.hrefs, base_url)


def fetch_form4_xml(client: SecClient, filing_url: str) -> Optional[str]:
    """Fetch Form 4 ownership XML for a filing index URL. Returns None on failure."""
    directory = filing_directory_url(filing_url)
    if directory is None:
        logger.warning("Cannot derive filing directory from url=%s", filing_url)
        return None

    try:
        index_resp = client.get(filing_url)
        xml_url = extract_xml_hrefs_from_index(index_resp.text, directory)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch Form 4 index url=%s error=%s", filing_url, exc)
        return None

    if not xml_url:
        logger.warning("No Form 4 XML found in index url=%s", filing_url)
        return None

    try:
        xml_resp = client.get(xml_url)
        text = xml_resp.text
        if "<ownershipDocument" not in text and "<ownershipDocument>" not in text:
            # Still allow if root uses default namespace prefix quirks
            if "ownershipDocument" not in text:
                logger.warning("Downloaded XML is not ownershipDocument url=%s", xml_url)
                return None
        return text
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch Form 4 XML url=%s error=%s", xml_url, exc)
        return None
