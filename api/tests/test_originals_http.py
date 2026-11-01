"""Original narrations: readable by the owner, sealed at rest, never part of what a model sees."""

from __future__ import annotations

from datetime import date
from typing import Any

from cfo.api.app import create_app
from cfo.ledger.repositories.db import Database
from cfo.testing import FIXTURE_DIR, SeedClient
from cfo.testing.api import PersonClient, person_client
from cfo.vault import FernetVault, generate_key

TODAY = date(2026, 10, 3)
ORIGINAL = "UPI-TEST CAFE-TESTCAFE-REF000009-UPI"


def app_client(database: Database, vault: FernetVault | None) -> PersonClient:
    return person_client(
        database, create_app(db=database, client=SeedClient(), clock=lambda: TODAY, vault=vault)
    )


def upload(api: Any) -> None:
    acc = api.post(
        "/accounts", json={"type": "savings", "institution": "HDFC Bank", "name": "HDFC"}
    ).json()
    api.post(
        f"/accounts/{acc['id']}/uploads",
        files={"file": ("s.csv", (FIXTURE_DIR / "hdfc_bank_sep.csv").read_bytes())},
    )


def test_owner_sees_the_original_beside_the_stored_narration(database: Database) -> None:
    key = generate_key()
    api = app_client(database, FernetVault(key))
    upload(api)
    rows = api.get("/transactions", params={"q": "CAFE"}).json()
    originals = {r["original"] for r in rows if r["original"]}
    assert ORIGINAL in originals
    cafe = next(r for r in rows if r["original"] == ORIGINAL)
    assert cafe["narration"] != ORIGINAL  # the stored text is the redacted one


def test_a_lost_key_degrades_to_the_redacted_text_without_an_error(database: Database) -> None:
    upload(app_client(database, FernetVault(generate_key())))
    other = app_client(database, FernetVault(generate_key()))
    rows = other.get("/transactions").json()
    assert rows and all(r["original"] is None for r in rows)
    assert other.get("/inbox").status_code == 200


def test_no_vault_means_no_originals_kept_or_shown(database: Database) -> None:
    api = app_client(database, None)
    upload(api)
    assert all(r["original"] is None for r in api.get("/transactions").json())


def test_originals_never_appear_in_the_model_preview(database: Database) -> None:
    api = app_client(database, FernetVault(generate_key()))
    upload(api)
    preview = api.get("/privacy/preview")
    assert preview.status_code == 200
    assert "REF000009" not in preview.text  # redaction removed it; the sealed original has it
