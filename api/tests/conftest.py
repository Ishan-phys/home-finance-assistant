from __future__ import annotations

from datetime import date

import pytest
from cfo.api.app import create_app
from cfo.api.auth import hash_password
from cfo.ledger.repositories.db import Database
from cfo.testing import SeedClient
from cfo.testing.api import OWNER_PASSWORD, OWNER_USERNAME, PersonClient, person_client

TODAY = date(2026, 10, 3)
_OWNER_HASH = hash_password(OWNER_PASSWORD)  # once per run: scrypt is deliberately slow


@pytest.fixture(autouse=True)
def owner_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every app a test builds reads these: one owner, a fixed secret, the usual cookie."""
    monkeypatch.setenv("OWNER_USERNAME", OWNER_USERNAME)
    monkeypatch.setenv("OWNER_PASSWORD_HASH", _OWNER_HASH)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-that-is-long-enough")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")


@pytest.fixture
def api(database: Database) -> PersonClient:
    """The default test person's client, over an app with the seeded categorizer."""
    return person_client(
        database, create_app(db=database, client=SeedClient(), clock=lambda: TODAY)
    )
