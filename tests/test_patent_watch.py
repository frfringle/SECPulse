"""Patent watch v1 — assignee map, ODP parse, poller dedupe (mocked USPTO)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import PatentEvent
from backend.patents.assignee_map import AssigneeMap, normalize_assignee
from backend.patents.client import UsptoClient, parse_odp_record
from backend.patents.poller import PatentPoller, make_dedupe_key
from backend.sec.rate_limiter import RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def engine(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'patents.db'}"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session_factory(engine):
    def factory() -> Session:
        return Session(engine)

    return factory


@pytest.fixture
def assignee_map(tmp_path: Path) -> AssigneeMap:
    src = Path(__file__).resolve().parents[1] / "data" / "assignee_aliases.json"
    dest = tmp_path / "assignee_aliases.json"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    m = AssigneeMap(dest)
    assert m.load() >= 1
    return m


def test_normalize_assignee_strips_suffixes():
    assert normalize_assignee("Apple Inc.") == normalize_assignee("Apple Incorporated")


def test_assignee_map_resolves_ttmi(assignee_map: AssigneeMap):
    hit = assignee_map.resolve("TTM Technologies, Inc")
    assert hit is not None
    assert hit.ticker == "TTMI"


def test_parse_odp_record_classifies_grant_and_app():
    sample = json.loads((FIXTURES / "uspto_search_sample.json").read_text(encoding="utf-8"))
    bags = sample["patentFileWrapperDataBag"]
    app = parse_odp_record(bags[0])
    grant = parse_odp_record(bags[1])
    assert app["event_type"] == "application_published"
    assert app["application_number"] == "18111222"
    assert grant["event_type"] == "grant"
    assert grant["patent_number"] == "12123456"
    assert grant["google_patents_url"]


def test_poller_ingests_and_dedupes(assignee_map: AssigneeMap, session_factory, engine):
    sample = json.loads((FIXTURES / "uspto_search_sample.json").read_text(encoding="utf-8"))

    def search_fn(body: dict) -> dict:
        return sample

    client = UsptoClient(
        "test-key",
        rate_limiter=RateLimiter(10),
        search_fn=search_fn,
    )
    poller = PatentPoller(
        client=client,
        assignee_map=assignee_map,
        session_factory=session_factory,
        per_assignee_limit=10,
    )
    n1 = poller.ingest_records(sample["patentFileWrapperDataBag"])
    n2 = poller.ingest_records(sample["patentFileWrapperDataBag"])
    assert n1 == 2
    assert n2 == 0
    with Session(engine) as s:
        rows = list(s.exec(select(PatentEvent)).all())
    assert len(rows) == 2
    by_type = {r.event_type: r for r in rows}
    assert by_type["grant"].actionable is True
    assert by_type["application_published"].actionable is False
    assert by_type["grant"].ticker == "TTMI"
    assert make_dedupe_key("17199888", "grant", "12123456") == by_type["grant"].dedupe_key


def test_uspto_client_requires_key():
    with pytest.raises(ValueError):
        UsptoClient("")
