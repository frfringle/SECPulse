"""Tests for Form 4 XML parsing and alert-by-rule classification."""

from __future__ import annotations

from pathlib import Path

from backend.sec.form4 import parse_form4_xml
from backend.sec.form4_fetch import (
    extract_xml_hrefs_from_index,
    filing_directory_url,
    pick_ownership_xml_href,
)


def test_officer_open_market_buy_alerts(fixtures_dir: Path):
    xml = (fixtures_dir / "form4_officer_open_market_buy.xml").read_text()
    result = parse_form4_xml(xml)

    assert result.insider.name == "Jane Officer"
    assert result.insider.is_officer is True
    assert result.insider.is_director is False
    assert result.insider.officer_title == "Chief Financial Officer"
    assert result.insider.role == "Officer: Chief Financial Officer"

    assert len(result.transactions) == 1
    txn = result.transactions[0]
    assert txn.transaction_code == "P"
    assert txn.shares == 1000
    assert txn.price == 250.50
    assert txn.total_value == 250500.0
    assert txn.alert_by_rule is True
    assert txn.skip_reason is None
    assert result.alert_transactions == [txn]


def test_director_open_market_buy_alerts(fixtures_dir: Path):
    xml = (fixtures_dir / "form4_director_open_market_buy.xml").read_text()
    result = parse_form4_xml(xml)

    assert result.insider.name == "Alex Director"
    assert result.insider.is_director is True
    assert result.insider.is_officer is False
    assert result.issuer_ticker == "AAPL"

    txn = result.transactions[0]
    assert txn.transaction_code == "P"
    assert txn.shares == 500
    assert txn.price == 180.0
    assert txn.total_value == 90000.0
    assert txn.alert_by_rule is True


def test_grants_and_10b5_1_sales_ignored(fixtures_dir: Path):
    xml = (fixtures_dir / "form4_grant_and_10b51_sale.xml").read_text()
    result = parse_form4_xml(xml)

    assert result.insider.is_officer and result.insider.is_director
    assert len(result.transactions) == 2
    assert result.alert_transactions == []

    grant, sale = result.transactions
    assert grant.transaction_code == "A"
    assert grant.alert_by_rule is False
    assert grant.skip_reason == "grant"

    assert sale.transaction_code == "S"
    assert sale.is_10b5_1 is True
    assert sale.alert_by_rule is False
    assert sale.skip_reason == "10b5-1_sale"
    assert sale.total_value == 840000.0


def test_ten_percent_buy_not_alert_by_rule(fixtures_dir: Path):
    xml = (fixtures_dir / "form4_ten_percent_buy.xml").read_text()
    result = parse_form4_xml(xml)

    assert result.insider.is_ten_percent_owner is True
    assert result.insider.is_officer is False
    assert result.insider.is_director is False
    txn = result.transactions[0]
    assert txn.transaction_code == "P"
    assert txn.alert_by_rule is False
    assert txn.skip_reason == "not_officer_or_director"


def test_document_level_aff10b5_one_marks_sale(fixtures_dir: Path, tmp_path: Path):
    # Minimal sale with document-level aff10b5One=1
    xml = """<?xml version="1.0"?>
    <ownershipDocument>
      <documentType>4</documentType>
      <issuer>
        <issuerCik>0000320193</issuerCik>
        <issuerName>Apple Inc.</issuerName>
        <issuerTradingSymbol>AAPL</issuerTradingSymbol>
      </issuer>
      <reportingOwner>
        <reportingOwnerId><rptOwnerName>Sam Seller</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship>
          <isDirector>0</isDirector><isOfficer>1</isOfficer>
          <isTenPercentOwner>0</isTenPercentOwner><isOther>0</isOther>
          <officerTitle>SVP</officerTitle>
        </reportingOwnerRelationship>
      </reportingOwner>
      <aff10b5One>1</aff10b5One>
      <nonDerivativeTable>
        <nonDerivativeTransaction>
          <securityTitle><value>Common Stock</value></securityTitle>
          <transactionDate><value>2026-10-20</value></transactionDate>
          <transactionCoding>
            <transactionCode>S</transactionCode>
          </transactionCoding>
          <transactionAmounts>
            <transactionShares><value>100</value></transactionShares>
            <transactionPricePerShare><value>10</value></transactionPricePerShare>
            <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
          </transactionAmounts>
        </nonDerivativeTransaction>
      </nonDerivativeTable>
    </ownershipDocument>
    """
    result = parse_form4_xml(xml)
    assert result.document_aff_10b5_1 is True
    assert result.transactions[0].is_10b5_1 is True
    assert result.transactions[0].alert_by_rule is False
    assert result.transactions[0].skip_reason == "10b5-1_sale"


def test_pick_ownership_xml_skips_xsl():
    hrefs = [
        "xslF345X05/wk-form4_20261027.xml",
        "wk-form4_20261027.xml",
        "exhibit99.htm",
    ]
    chosen = pick_ownership_xml_href(
        hrefs, "https://www.sec.gov/Archives/edgar/data/1318605/000131860526000010/"
    )
    assert chosen is not None
    assert chosen.endswith("wk-form4_20261027.xml")
    assert "xslF345" not in chosen


def test_extract_xml_from_index_fixture(fixtures_dir: Path):
    html = (fixtures_dir / "form4_index.htm").read_text()
    base = "https://www.sec.gov/Archives/edgar/data/1318605/000131860526000010/"
    url = extract_xml_hrefs_from_index(html, base)
    assert url == base + "wk-form4_20261027.xml"


def test_filing_directory_url():
    url = (
        "https://www.sec.gov/Archives/edgar/data/1318605/000131860526000010/"
        "0001318605-26-000010-index.htm"
    )
    assert (
        filing_directory_url(url)
        == "https://www.sec.gov/Archives/edgar/data/1318605/000131860526000010/"
    )
