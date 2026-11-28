"""Database connection and session management for MUHR Registry."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator, Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

logger = logging.getLogger(__name__)

engine: Engine
SessionLocal: sessionmaker


def configure(url: str | None = None) -> None:
    """(Re)build the engine. Tests call this with a temporary SQLite URL."""
    global engine, SessionLocal
    url = url or os.getenv("DATABASE_URL", "sqlite:///./muhr.db")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


configure()


# Lightweight SQLite migrations: every column added to an existing table after
# the initial schema must be listed, otherwise old `muhr.db` files break.
_PENDING_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "jobs": [
        ("seller_committed_hash", "VARCHAR(64)"),
        ("lightning_payment_hash", "VARCHAR(64)"),
        ("lightning_mode", "VARCHAR(8)"),
        ("accepted_price_sats", "INTEGER"),
        ("key_commitment", "VARCHAR(64)"),
        ("ciphertext_hash", "VARCHAR(64)"),
        ("key_release", "VARCHAR(32)"),
        ("bolt11", "TEXT"),
        ("payment_verified", "BOOLEAN NOT NULL DEFAULT 0"),
        ("payment_verified_by", "VARCHAR(32)"),
        ("received_at", "DATETIME"),
        ("paid_at", "DATETIME"),
        ("failure_reason", "VARCHAR(500)"),
    ],
    "sellers": [
        ("api_key_hash", "VARCHAR(64)"),
        ("stake_verified", "BOOLEAN NOT NULL DEFAULT 0"),
        ("jobs_failed", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "transactions": [
        ("mode", "VARCHAR(8)"),
    ],
}


def _run_lightweight_migrations() -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _PENDING_COLUMNS.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col_name, col_type in cols:
                if col_name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                logger.info("Migrated DB: added %s.%s (%s)", table, col_name, col_type)


def init_db() -> None:
    """Create all tables and apply lightweight migrations (idempotent)."""
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()
    logger.info("Database initialized")


@contextmanager
def get_db() -> Iterator[Session]:
    """Session with automatic commit/rollback for background jobs."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
