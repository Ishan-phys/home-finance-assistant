"""Deleting a person removes their whole ledger and nothing of anyone else's."""

from __future__ import annotations

from datetime import date

from cfo.api.app import create_app
from cfo.ledger.repositories.db import Database
from cfo.testing import FIXTURE_DIR, SeedClient
from cfo.testing.api import signed_in_client
from fastapi.testclient import TestClient

TODAY = date(2026, 10, 3)


def client(database: Database) -> TestClient:
    return signed_in_client(create_app(db=database, client=SeedClient(), clock=lambda: TODAY))


def person_with_statement(c: TestClient, name: str) -> str:
    person = c.post("/people", json={"name": name}).json()["id"]
    account = c.post(
        f"/people/{person}/accounts",
        json={
            "type": "savings",
            "institution": "SBI",
            "name": "SBI Savings",
            "opening_value_paise": 0,
            "opening_date": "2026-08-31",
        },
    )
    assert account.status_code == 201, account.text
    assert c.post(f"/people/{person}/setup/complete").status_code == 200
    sent = c.post(
        f"/people/{person}/accounts/{account.json()['id']}/uploads",
        files={"file": ("sbi_bank_sep.xlsx", (FIXTURE_DIR / "sbi_bank_sep.xlsx").read_bytes())},
    )
    assert sent.status_code == 200, sent.text
    return str(person)


def test_delete_a_person_with_statements_leaves_the_other_person_intact(database: Database) -> None:
    c = client(database)
    keep = person_with_statement(c, "Asha Rao")
    drop = person_with_statement(c, "Pavani Priya")
    before = c.get(f"/people/{keep}/accounts").json()

    assert c.delete(f"/people/{drop}").status_code == 204

    ids = [p["id"] for p in c.get("/people").json()]
    assert keep in ids and drop not in ids
    assert c.get(f"/people/{drop}/accounts").status_code == 404
    assert c.get(f"/people/{keep}/accounts").json() == before
    assert c.delete(f"/people/{drop}").status_code == 404
