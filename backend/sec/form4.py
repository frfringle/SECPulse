"""Parse SEC Form 4 ownership XML (no LLM).

Extracts insider identity/role and non-derivative transactions. Flags
open-market purchases (code P) by officers or directors as alert-by-rule
candidates. Grants (code A) and 10b5-1 sales are ignored for that path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from xml.etree import ElementTree as ET

# Transaction codes we care about for storage / alerting
CODE_OPEN_MARKET_BUY = "P"
CODE_OPEN_MARKET_SALE = "S"
CODE_GRANT = "A"

_TRUE_VALUES = {"1", "true", "yes", "y"}
_TENB51_RE = re.compile(r"10\s*b\s*[- ]?\s*5\s*[- ]?\s*1", re.IGNORECASE)


@dataclass(frozen=True)
class Form4Insider:
    name: str
    role: str  # e.g. "Officer: CEO", "Director", "Officer / Director"
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool
    officer_title: str = ""


@dataclass(frozen=True)
class Form4Transaction:
    """One non-derivative transaction row from a Form 4."""

    transaction_code: str
    shares: float
    price: Optional[float]
    total_value: Optional[float]
    acquired_disposed: str  # A or D
    security_title: str
    transaction_date: str
    is_10b5_1: bool
    alert_by_rule: bool
    skip_reason: Optional[str] = None


@dataclass
class Form4ParseResult:
    issuer_cik: str
    issuer_name: str
    issuer_ticker: str
    period_of_report: str
    document_aff_10b5_1: bool
    insider: Form4Insider
    transactions: list[Form4Transaction] = field(default_factory=list)

    @property
    def alert_transactions(self) -> list[Form4Transaction]:
        return [t for t in self.transactions if t.alert_by_rule]


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _child(parent: ET.Element, name: str) -> Optional[ET.Element]:
    for child in parent:
        if _local(child.tag) == name:
            return child
    return None


def _children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in parent if _local(c.tag) == name]


def _text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    if el.text and el.text.strip():
        return el.text.strip()
    # Common SEC pattern: <foo><value>X</value></foo>
    value = _child(el, "value")
    if value is not None and value.text:
        return value.text.strip()
    return (el.text or "").strip()


def _boolish(raw: str) -> bool:
    return raw.strip().lower() in _TRUE_VALUES


def _float_or_none(raw: str) -> Optional[float]:
    cleaned = (raw or "").strip().replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _collect_footnotes(root: ET.Element) -> dict[str, str]:
    """Map footnote id -> text from <footnotes><footnote id="F1">...</footnote>."""
    notes: dict[str, str] = {}
    for el in root.iter():
        if _local(el.tag) != "footnote":
            continue
        fid = el.get("id") or ""
        if fid:
            notes[fid] = "".join(el.itertext()).strip()
    return notes


def _footnote_ids_under(el: ET.Element) -> list[str]:
    ids: list[str] = []
    for child in el.iter():
        if _local(child.tag) == "footnoteId":
            ref = child.get("id") or _text(child)
            if ref:
                ids.append(ref)
    return ids


def _mentions_10b5_1(text: str) -> bool:
    return bool(_TENB51_RE.search(text or ""))


def _role_label(
    is_director: bool,
    is_officer: bool,
    officer_title: str,
    is_ten_percent: bool,
    is_other: bool,
    other_text: str = "",
) -> str:
    parts: list[str] = []
    if is_officer:
        parts.append(f"Officer: {officer_title}" if officer_title else "Officer")
    if is_director:
        parts.append("Director")
    if is_ten_percent:
        parts.append("10% Owner")
    if is_other:
        parts.append(other_text or "Other")
    return " / ".join(parts) if parts else "Unknown"


def _parse_insider(root: ET.Element) -> Form4Insider:
    owner = _child(root, "reportingOwner")
    if owner is None:
        # Some filings nest multiple; take the first reportingOwner anywhere
        for el in root.iter():
            if _local(el.tag) == "reportingOwner":
                owner = el
                break
    if owner is None:
        return Form4Insider(
            name="",
            role="Unknown",
            is_director=False,
            is_officer=False,
            is_ten_percent_owner=False,
        )

    owner_id = _child(owner, "reportingOwnerId")
    name = _text(_child(owner_id, "rptOwnerName")) if owner_id is not None else ""

    rel = _child(owner, "reportingOwnerRelationship")
    is_director = _boolish(_text(_child(rel, "isDirector"))) if rel is not None else False
    is_officer = _boolish(_text(_child(rel, "isOfficer"))) if rel is not None else False
    is_ten = (
        _boolish(_text(_child(rel, "isTenPercentOwner"))) if rel is not None else False
    )
    is_other = _boolish(_text(_child(rel, "isOther"))) if rel is not None else False
    officer_title = _text(_child(rel, "officerTitle")) if rel is not None else ""
    other_text = _text(_child(rel, "otherText")) if rel is not None else ""

    return Form4Insider(
        name=name,
        role=_role_label(
            is_director, is_officer, officer_title, is_ten, is_other, other_text
        ),
        is_director=is_director,
        is_officer=is_officer,
        is_ten_percent_owner=is_ten,
        officer_title=officer_title,
    )


def _txn_is_10b5_1(
    txn: ET.Element,
    document_aff: bool,
    footnotes: dict[str, str],
) -> bool:
    if document_aff:
        return True
    for fid in _footnote_ids_under(txn):
        if _mentions_10b5_1(footnotes.get(fid, "")):
            return True
    # Rare: inline text
    if _mentions_10b5_1("".join(txn.itertext())):
        return True
    return False


def _classify_transaction(
    code: str,
    shares: float,
    price: Optional[float],
    acquired_disposed: str,
    is_10b5_1: bool,
    insider: Form4Insider,
) -> tuple[bool, Optional[str]]:
    """Return (alert_by_rule, skip_reason)."""
    if code == CODE_GRANT:
        return False, "grant"
    if code == CODE_OPEN_MARKET_SALE and is_10b5_1:
        return False, "10b5-1_sale"
    if code != CODE_OPEN_MARKET_BUY:
        return False, f"non_alert_code_{code}"
    if is_10b5_1:
        # Unusual but treat planned buys as non-rule alerts for now
        return False, "10b5-1_buy"
    if not (insider.is_officer or insider.is_director):
        return False, "not_officer_or_director"
    if shares <= 0:
        return False, "zero_shares"
    return True, None


def parse_form4_xml(xml_text: str) -> Form4ParseResult:
    """Parse a Form 4 ownershipDocument XML string."""
    root = ET.fromstring(xml_text)
    # Allow root itself to be ownershipDocument or wrap it
    if _local(root.tag) != "ownershipDocument":
        found = None
        for el in root.iter():
            if _local(el.tag) == "ownershipDocument":
                found = el
                break
        if found is None:
            raise ValueError("Not a Form 4 ownershipDocument")
        root = found

    issuer = _child(root, "issuer")
    issuer_cik = _text(_child(issuer, "issuerCik")) if issuer is not None else ""
    issuer_name = _text(_child(issuer, "issuerName")) if issuer is not None else ""
    issuer_ticker = (
        _text(_child(issuer, "issuerTradingSymbol")) if issuer is not None else ""
    )
    period = _text(_child(root, "periodOfReport"))
    document_aff = _boolish(_text(_child(root, "aff10b5One")))
    footnotes = _collect_footnotes(root)
    insider = _parse_insider(root)

    transactions: list[Form4Transaction] = []
    table = _child(root, "nonDerivativeTable")
    txn_nodes: list[ET.Element] = []
    if table is not None:
        txn_nodes.extend(_children(table, "nonDerivativeTransaction"))
    else:
        # Fallback: any nonDerivativeTransaction under root
        for el in root.iter():
            if _local(el.tag) == "nonDerivativeTransaction":
                txn_nodes.append(el)

    for txn in txn_nodes:
        coding = _child(txn, "transactionCoding")
        code = (
            _text(_child(coding, "transactionCode")).upper()
            if coding is not None
            else ""
        )
        amounts = _child(txn, "transactionAmounts")
        shares = (
            _float_or_none(_text(_child(amounts, "transactionShares"))) or 0.0
            if amounts is not None
            else 0.0
        )
        price = (
            _float_or_none(_text(_child(amounts, "transactionPricePerShare")))
            if amounts is not None
            else None
        )
        acquired = (
            _text(_child(amounts, "transactionAcquiredDisposedCode")).upper()
            if amounts is not None
            else ""
        )
        security = _text(_child(txn, "securityTitle"))
        tx_date = _text(_child(txn, "transactionDate"))
        is_10b5_1 = _txn_is_10b5_1(txn, document_aff, footnotes)
        total_value = None
        if price is not None and shares:
            total_value = round(shares * price, 4)

        alert, skip_reason = _classify_transaction(
            code, shares, price, acquired, is_10b5_1, insider
        )
        transactions.append(
            Form4Transaction(
                transaction_code=code,
                shares=shares,
                price=price,
                total_value=total_value,
                acquired_disposed=acquired,
                security_title=security,
                transaction_date=tx_date,
                is_10b5_1=is_10b5_1,
                alert_by_rule=alert,
                skip_reason=skip_reason,
            )
        )

    return Form4ParseResult(
        issuer_cik=issuer_cik.zfill(10) if issuer_cik.isdigit() else issuer_cik,
        issuer_name=issuer_name,
        issuer_ticker=issuer_ticker.upper(),
        period_of_report=period,
        document_aff_10b5_1=document_aff,
        insider=insider,
        transactions=transactions,
    )
