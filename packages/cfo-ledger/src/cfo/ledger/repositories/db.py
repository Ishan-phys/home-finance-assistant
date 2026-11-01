"""Engine and transaction scope. Every upload and owner action runs in one transaction."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

from cfo.core.types import Scope
from cfo.ledger.repositories.scope import SCOPE_KEY
from sqlalchemy import CursorResult, Engine, create_engine, text
from sqlalchemy.orm import Session

UPLOAD_LOCK_KEY = int.from_bytes(hashlib.sha256(b"cfo:upload").digest()[:8], "big", signed=True)


class Database:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            # A failed statement's message would otherwise carry its bound values, which are
            # narrations and amounts, into logs.
            hide_parameters=True,
        )
        # Used when a transaction names no scope. The application never sets it: every request
        # names its person's ledger. Tests set it to their own ledger.
        self.default_scope: Scope | None = None

    @contextmanager
    def transaction(self, scope: Scope | None = None) -> Iterator[Session]:
        """Commit on success, roll back on any exception. The scope bounds every repository
        built on the session."""
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            chosen = scope or self.default_scope
            if chosen is not None:
                session.info[SCOPE_KEY] = chosen
            yield session

    @contextmanager
    def upload_lock(self) -> Iterator[None]:
        """Serialize uploads. A session-level advisory lock on a dedicated connection is held
        across the whole pipeline, including categorization, which runs before the database
        transaction opens, so two files cannot race through transfer matching."""
        with self.engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": UPLOAD_LOCK_KEY})
            try:
                yield
            finally:
                conn.rollback()
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": UPLOAD_LOCK_KEY})
                conn.commit()

    def dispose(self) -> None:
        self.engine.dispose()


def rowcount(result: object) -> int:
    """Rows matched by an UPDATE or DELETE."""
    return int(cast("CursorResult[Any]", result).rowcount)
