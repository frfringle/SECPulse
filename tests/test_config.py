"""Tests for required SEC_USER_AGENT configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.config import Settings


def test_settings_requires_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_rejects_bad_user_agent(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "not-an-email")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_accepts_valid_user_agent(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "SECPulse Dev dev@example.com")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.sec_user_agent == "SECPulse Dev dev@example.com"
