"""Application configuration loaded from environment / .env."""

from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# SEC fair-access User-Agent must look like: "Name email@example.com"
_UA_PATTERN = re.compile(
    r"^.+\s+[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\s*$"
)

WATCHED_FORMS = frozenset({"8-K", "8-K/A", "4", "SC 13D", "SC 13D/A"})

ATOM_FEED_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&output=atom"
)
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


class Settings(BaseSettings):
    """Runtime settings. Refuses to construct without a valid SEC_USER_AGENT."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sec_user_agent: str = Field(..., alias="SEC_USER_AGENT")
    database_url: str = Field(
        default="sqlite:///./data/secpulse.db",
        alias="DATABASE_URL",
    )
    poll_interval_seconds: int = Field(default=30, alias="POLL_INTERVAL_SECONDS")
    sec_max_requests_per_second: float = Field(
        default=8.0,
        alias="SEC_MAX_REQUESTS_PER_SECOND",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    ticker_cache_path: Path = Field(
        default=PROJECT_ROOT / "data" / "ticker_cache.json",
    )

    @field_validator("sec_user_agent")
    @classmethod
    def validate_user_agent(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned or not _UA_PATTERN.match(cleaned):
            raise ValueError(
                'SEC_USER_AGENT must be set to "Name email@example.com" '
                "(company/person name plus a contact email)."
            )
        return cleaned


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings. Raises ValidationError if SEC_USER_AGENT is missing."""
    return Settings()  # type: ignore[call-arg]


def require_settings() -> Settings:
    """Load settings or exit the process with a clear message."""
    try:
        return get_settings()
    except Exception as exc:  # noqa: BLE001 — surface pydantic ValidationError cleanly
        print(
            "SECPulse refused to start: SEC_USER_AGENT is required "
            'and must look like "Name email@example.com".\n'
            f"Detail: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
