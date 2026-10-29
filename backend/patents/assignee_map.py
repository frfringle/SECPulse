"""Assignee name → ticker alias map (manual seed + normalize)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_STRIP = re.compile(r"[^a-z0-9]+")


def normalize_assignee(name: str) -> str:
    s = (name or "").lower().strip()
    s = " ".join(_STRIP.sub(" ", s).split())
    for noise in (
        " incorporated",
        " corporation",
        " company",
        " limited",
        " llc",
        " inc",
        " corp",
        " ltd",
        " co",
    ):
        if s.endswith(noise):
            s = s[: -len(noise)].strip()
    return s


@dataclass(frozen=True)
class AssigneeHit:
    ticker: str
    company_name: str
    matched_alias: str


class AssigneeMap:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._by_norm: dict[str, AssigneeHit] = {}

    def load(self) -> int:
        if not self.path.is_file():
            logger.warning("Assignee alias file missing path=%s", self.path)
            self._by_norm = {}
            return 0
        data = json.loads(self.path.read_text(encoding="utf-8"))
        aliases = data.get("aliases") or []
        mapping: dict[str, AssigneeHit] = {}
        for row in aliases:
            assignee = str(row.get("assignee") or "").strip()
            ticker = str(row.get("ticker") or "").strip().upper()
            company = str(row.get("company_name") or assignee).strip()
            if not assignee or not ticker:
                continue
            hit = AssigneeHit(ticker=ticker, company_name=company, matched_alias=assignee)
            mapping[normalize_assignee(assignee)] = hit
        self._by_norm = mapping
        logger.info("Assignee map ready aliases=%s path=%s", len(mapping), self.path)
        return len(mapping)

    def resolve(self, assignee: str) -> Optional[AssigneeHit]:
        key = normalize_assignee(assignee)
        if not key:
            return None
        hit = self._by_norm.get(key)
        if hit:
            return hit
        # Prefix / contains soft match against known aliases
        for alias_key, alias_hit in self._by_norm.items():
            if alias_key and (alias_key in key or key in alias_key):
                return alias_hit
        return None
