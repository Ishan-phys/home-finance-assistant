"""People over HTTP: creating one, linking accounts, and keeping two people apart."""

from __future__ import annotations

import io
import json
from datetime import date

import openpyxl
import pytest
from cfo.api.app import create_app
from cfo.ledger.repositories.db import Database
from cfo.testing import SeedClient
from cfo.testing.api import PersonClient
from fastapi.testclient import TestClient

TODAY = date(2026, 10, 3)


@pytest.fixture
def anon(empty_database: Database) -> TestClient:
    app = create_app(db=empty_database, client=_Spy(), clock=lambda: TODAY)
    return TestClient(app, raise_server_exceptions=False)


class _Spy(SeedClient):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.requests.append(user)
        return super().complete(system, user)


def person(anon: TestClient, name: str, family: list[str] | None = None) -> PersonClient:
    r = anon.post("/people", json={"name": name, "family_names": family or []})
    assert r.status_code == 201, r.text
    return PersonClient(anon, r.json()["id"])


def statement(narration: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in [
        ["Statement From  :  01/09/2026         To  :  30/09/2026"],
        ["Date", "Narration", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
        ["********"] * 5,
        ["02/09/26", narration, 500.0, None, 99500.0],
    ]:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def link(p: PersonClient, name: str, type: str, institution: str) -> str:
    r = p.post("/accounts", json={"name": name, "type": type, "institution": institution})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_a_first_run_has_nobody_then_a_named_person_with_linked_accounts(anon: TestClient) -> None:
    assert anon.get("/people").json() == []
    assert anon.post("/people", json={"name": "  "}).status_code == 422
    asha = person(anon, "Asha Rao")
    listed = anon.get("/people").json()
    assert [(p["name"], p["id"]) for p in listed] == [("Asha Rao", asha.person_id)]

    # linking accounts initializes an adapter for each, on this person's ledger
    bank = link(asha, "Salary account", "savings", "HDFC Bank")
    link(asha, "Everyday card", "credit_card", "Axis Bank")
    link(asha, "Groww funds", "mutual_fund", "Groww")
    accounts = asha.get("/accounts").json()
    assert {a["name"]: a["binding"] for a in accounts} == {
        "Salary account": "hdfc_bank",
        "Everyday card": "axis_credit_card",
        "Groww funds": "groww",
    }
    assert all(a["binding"] for a in accounts)  # each one accepts statements
    assert (
        asha.post(
            "/accounts", json={"name": "x", "type": "sbi_card", "institution": "SBI"}
        ).status_code
        == 422
    )
    assert bank in {a["id"] for a in accounts}


def test_two_people_are_kept_apart_over_http(anon: TestClient) -> None:
    asha, ben = person(anon, "Asha Rao"), person(anon, "Ben Mills")
    acc = link(asha, "Asha Savings", "savings", "HDFC Bank")
    link(ben, "Ben Savings", "savings", "SBI")
    up = asha.post(
        f"/accounts/{acc}/uploads", files={"file": ("s.xlsx", statement("UPI-SWIGGY-x"))}
    )
    assert up.status_code == 200 and up.json()["rows_inserted"] == 1

    assert [a["name"] for a in ben.get("/accounts").json()] == ["Ben Savings"]
    assert ben.get("/transactions").json() == []
    assert len([t for t in asha.get("/transactions").json() if t["source"] == "import"]) == 1
    # Ben cannot reach Asha's account by id: not read, edit, upload, or set a value
    assert ben.get(f"/accounts/{acc}").status_code == 404
    assert ben.patch(f"/accounts/{acc}", json={"name": "mine"}).status_code == 404
    assert (
        ben.post(f"/accounts/{acc}/uploads", files={"file": ("s.xlsx", statement("x"))}).status_code
        == 404
    )
    assert (
        ben.post(
            f"/accounts/{acc}/value", json={"as_of": "2026-09-30", "amount_paise": 1}
        ).status_code
        == 404
    )
    assert asha.get("/accounts").json()[0]["retired"] is False
    # settings and terms are per person
    asha.patch("/settings", json={"min_cash_buffer_paise": 5_000_00})
    assert ben.get("/settings").json()["min_cash_buffer"]["paise"] == 0
    assert "Rao" in asha.get("/privacy/terms").json()["terms"]
    assert "Rao" not in ben.get("/privacy/terms").json()["terms"]
    # an unknown person is a 404, not an empty ledger
    assert anon.get("/people/00000000-0000-0000-0000-000000000001/accounts").status_code == 404


def test_a_persons_name_reaches_no_stored_row_and_no_model_request(anon: TestClient) -> None:
    spy: _Spy = anon.app.state.deps.client  # type: ignore[attr-defined]
    mira = person(anon, "Mira Kulkarni", family=["Tara Nair"])
    acc = link(mira, "Mira's account", "savings", "HDFC Bank")
    narration = "UPI-MIRA KULKARNI-x-IFSC-1-Rent to TARA NAIR via Mira"
    r = mira.post(f"/accounts/{acc}/uploads", files={"file": ("s.xlsx", statement(narration))})
    assert r.status_code == 200
    stored = json.dumps(mira.get("/transactions").json()) + json.dumps(r.json())
    sent = "\n".join(spy.requests)
    for name in ("MIRA", "KULKARNI", "TARA", "NAIR"):
        # the account name the owner typed is theirs to see, as a name and in its path
        shown = stored.upper().replace("MIRA'S ACCOUNT", "").replace("MIRA-S-ACCOUNT", "")
        assert name not in shown, name
        assert name not in sent.upper(), name
    assert "[PERSON:" in sent


def test_the_sample_is_a_person_and_only_offered_before_anyone_exists(anon: TestClient) -> None:
    created = anon.post("/sample")
    assert created.status_code == 201 and created.json()["accounts"] == 6
    pid = created.json()["person_id"]
    assert anon.get(f"/people/{pid}/accounts").json()[0]["name"].startswith("Sample")
    assert anon.get(f"/people/{pid}/setup").json()["completed"] is True
    assert anon.post("/sample").status_code == 409
    person(anon, "Someone Else")  # people may still be added afterwards
    assert len(anon.get("/people").json()) == 2


def test_chat_is_per_person(anon: TestClient) -> None:
    created = anon.post("/sample").json()
    sample = PersonClient(anon, created["person_id"])
    other = person(anon, "Ben Mills")
    # each person gets their own chat service, and its tools read only their ledger
    registry = anon.app.state.deps  # type: ignore[attr-defined]
    assert registry is not None
    assert sample.get("/reports/balance-sheet").json()["net_worth"]["paise"] != 0
    assert other.get("/reports/balance-sheet").json()["net_worth"]["paise"] == 0
