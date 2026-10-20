"""PostgreSQL fixtures. Set CFO_TEST_DATABASE_URL to reuse a running server; otherwise a
throwaway container is started with testcontainers."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from cfo.ledger.repositories.db import Database
from cfo.testing import LEDGER_PACKAGE
from sqlalchemy import create_engine, text


def alembic_config(url: str):  # type: ignore[no-untyped-def]

    cfg = Config(str(LEDGER_PACKAGE / "alembic.ini"))
    cfg.set_main_option("script_location", str(LEDGER_PACKAGE / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    explicit = os.environ.get("CFO_TEST_DATABASE_URL")
    if explicit:
        yield explicit
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(pg_url: str) -> str:

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_url
    try:
        command.upgrade(alembic_config(pg_url), "head")
    finally:
        if previous is None:
            del os.environ["DATABASE_URL"]
        else:
            os.environ["DATABASE_URL"] = previous
    return pg_url


@pytest.fixture(scope="session")
def _database(migrated_url: str):  # type: ignore[no-untyped-def]

    db = Database(migrated_url)
    yield db
    db.dispose()


def _truncate(db) -> None:  # type: ignore[no-untyped-def]

    with db.engine.begin() as conn:
        tables = conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " AND tablename <> 'alembic_version'"
            )
        ).scalars()
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    db.default_scope = None
    db.default_person_id = None


@pytest.fixture
def empty_database(_database):  # type: ignore[no-untyped-def]
    """A migrated database with nobody in it: the state of a first run."""
    _truncate(_database)
    return _database


@pytest.fixture
def database(_database):  # type: ignore[no-untyped-def]
    """A migrated database, emptied before each test that asks for it, with one person and ledger
    set as its default scope. Pure unit tests never ask, so they never start PostgreSQL.

    Tests that name no scope act on that ledger; tests of isolation create more people."""
    from cfo.core.types import Scope
    from cfo.ledger.repositories.people import PeopleRepository

    _truncate(_database)
    with _database.transaction() as s:
        person, ledger = PeopleRepository(s).create("Zelda Voss")
    _database.default_scope = Scope.of(ledger.id)
    _database.default_person_id = person.id
    return _database


@pytest.fixture
def admin_engine(pg_url: str):  # type: ignore[no-untyped-def]

    engine = create_engine(pg_url, isolation_level="AUTOCOMMIT")
    yield engine
    engine.dispose()
