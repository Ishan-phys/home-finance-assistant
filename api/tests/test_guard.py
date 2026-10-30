"""A website open in the owner's browser must not be able to drive the local API."""

from __future__ import annotations

from datetime import date

from cfo.api.app import create_app
from cfo.ledger.repositories.db import Database
from cfo.testing import SeedClient
from fastapi.testclient import TestClient

TODAY = date(2026, 10, 3)


def client(database: Database) -> TestClient:
    return TestClient(create_app(db=database, client=SeedClient(), clock=lambda: TODAY))


def test_a_foreign_host_header_is_refused(database: Database) -> None:
    c = client(database)
    assert c.get("/health", headers={"Host": "evil.example"}).status_code == 400  # DNS rebinding
    assert c.get("/health", headers={"Host": "localhost:3000"}).status_code == 200
    assert c.get("/health", headers={"Host": "api:8000"}).status_code == 200
    assert c.get("/health", headers={"Host": "127.0.0.1:8000"}).status_code == 200


def test_a_cross_site_write_is_refused_but_reads_and_same_site_writes_work(
    database: Database,
) -> None:
    c = client(database)
    body = {"name": "Mallory"}
    evil = c.post("/people", json=body, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403 and evil.json()["error"]["code"] == "FORBIDDEN_ORIGIN"
    assert (
        c.post("/people", json=body, headers={"Origin": "http://localhost:3000"}).status_code == 201
    )
    assert c.post("/people", json={"name": "Nobody"}).status_code == 201  # no Origin: not a browser
    assert (
        c.get("/people", headers={"Origin": "https://evil.example"}).status_code == 200
    )  # reads need CORS to be seen
