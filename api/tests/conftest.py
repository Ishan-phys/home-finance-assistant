from __future__ import annotations

from datetime import date

import pytest
from cfo.api.app import create_app
from cfo.ledger.repositories.db import Database
from cfo.testing import SeedClient
from cfo.testing.api import PersonClient, person_client

TODAY = date(2026, 10, 3)


@pytest.fixture
def api(database: Database) -> PersonClient:
    """The default test person's client, over an app with the seeded categorizer."""
    return person_client(
        database, create_app(db=database, client=SeedClient(), clock=lambda: TODAY)
    )
