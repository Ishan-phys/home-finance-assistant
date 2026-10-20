"""Spec 9.1 acceptance: what actually leaves the machine."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from cfo.core.types import AccountType
from cfo.ingest.upload import upload_statement
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.ledger.setup import AccountInput, add_account

TODAY = date(2026, 10, 3)
D = date.fromisoformat

# Private details that must never appear in any outbound request.
ACCOUNT_NAME = "Priya Regalia Savings"
INSTITUTION = "Acme Private Bank"
PHONE = "9876543210"

STATEMENT = (
    "Statement From : 01/09/2026 To : 30/09/2026\n"
    "Txn Date,Narration,Withdrawals,Deposits,Closing Balance\n"
    f'02/09/2026,UPI/{PHONE}/Rahul,500.00,,"99,500.00"\n'
    '03/09/2026,UPI/Swiggy/Order,250.00,,"99,250.00"\n'
    f'04/09/2026,UPI-ANITA SHARMA-anita.s@okhdfc-HDFC0001234-4012345678-Gift,100.00,,"99,150.00"\n'
).encode()


class Recorder:
    """A categorization model that records every request it is sent."""

    def __init__(self) -> None:
        self.requests: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.requests.append(system + "\n" + user)
        keys = {
            line.split(" — ")[0].split(": ", 1)[1]: line.split(": ", 1)[0]
            for line in system.splitlines()
            if " — " in line and ": " in line
        }
        items = []
        for line in user.splitlines():
            n, text = line.split(". ", 1)
            category = keys["Dining"] if "Swiggy" in text else keys["Shopping"]
            merchant = "Swiggy" if "Swiggy" in text else "Personal transfer"
            items.append({"id": int(n), "merchant": merchant, "category": category})
        return json.dumps({"items": items})


@pytest.fixture
def ledger(database: Database) -> dict[str, Any]:
    with database.transaction() as s:
        acc = add_account(
            s, AccountInput(AccountType.SAVINGS, INSTITUTION, ACCOUNT_NAME), TODAY, "hdfc_bank"
        )
    return {"account": acc.id}


def test_redacted_narrations_are_what_is_stored_and_what_is_sent(
    database: Database, ledger: dict[str, Any]
) -> None:
    rec = Recorder()
    upload_statement(database, ledger["account"], "s.csv", STATEMENT, rec, TODAY)
    sent = "\n".join(rec.requests)
    stored_rows = _stored(database)
    stored = "\n".join(f"{t.narration}\n{t.payee}" for t in stored_rows.values())
    for where, text in (("request", sent), ("ledger", stored)):
        for private in (PHONE, "Rahul", "ANITA", "SHARMA", "anita.s@okhdfc", "4012345678"):
            assert private not in text, (where, private)
        assert "UPI/Swiggy/Order" in text, where  # merchants stay readable
    for private in (ACCOUNT_NAME, INSTITUTION, "Priya", "Acme"):
        assert private not in sent, private
    assert "UPI/[PHONE:" in sent and "[PERSON:" in sent  # tokens stand in for the details
    swiggy = stored_rows["UPI/Swiggy/Order"]
    assert swiggy.payee == "Swiggy"
    person_rows = [t for t in stored_rows.values() if t.narration.startswith("UPI/[PHONE:")]
    assert len(person_rows) == 1 and person_rows[0].payee == "Personal transfer"


def test_the_same_payee_keeps_one_token_across_uploads(
    database: Database, ledger: dict[str, Any]
) -> None:
    first = STATEMENT
    again = STATEMENT.replace(b"02/09/2026", b"12/09/2026")  # the same payee, another day
    upload_statement(database, ledger["account"], "a.csv", first, None, TODAY)
    upload_statement(database, ledger["account"], "b.csv", again, None, TODAY)
    with database.transaction() as s:
        descriptions = [
            t.narration for t in JournalRepository(s).list_all() if t.source == "import"
        ]
    person = [d for d in descriptions if d.startswith("UPI/[PHONE:")]
    assert len(person) == 2 and person[0] == person[1]  # stable, so grouping and dedup work


def _stored(database: Database):  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        return {t.narration: t for t in JournalRepository(s).list_all() if t.source == "import"}
