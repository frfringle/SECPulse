"""SQLite engine and session helpers."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from backend.config import PROJECT_ROOT, get_settings


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    raw = database_url.removeprefix("sqlite:///")
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    _ensure_sqlite_parent(url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, echo=False, connect_args=connect_args)


engine = None


def init_db(database_url: str | None = None) -> None:
    """Create tables and set the module-level engine."""
    global engine
    engine = create_db_engine(database_url)
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    if engine is None:
        init_db()
    assert engine is not None
    with Session(engine) as session:
        yield session


def session_scope() -> Session:
    if engine is None:
        init_db()
    assert engine is not None
    return Session(engine)
