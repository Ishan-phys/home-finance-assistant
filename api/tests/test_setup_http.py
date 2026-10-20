"""Setup over HTTP: accounts and categories first, then statements (spec §5.0)."""

from __future__ import annotations

from typing import Any

from cfo.testing import FIXTURE_DIR


def fixture(name: str) -> tuple[str, bytes]:
    return (name, (FIXTURE_DIR / name).read_bytes())


def test_catalog_lists_types_and_institutions(api: Any) -> None:
    catalog = api.get("/catalog").json()
    types = {t["type"]: t for t in catalog["types"]}
    assert (
        types["credit_card"]["label"] == "Credit card" and types["fixed_deposit"]["manual"] is True
    )
    hdfc = next(i for i in catalog["institutions"] if i["name"] == "HDFC Bank")
    assert {a["type"]: a["binding"] for a in hdfc["accounts"]}["savings"] == "hdfc_bank"


def test_setup_flow_then_upload(api: Any) -> None:
    assert api.get("/setup").json() == {"completed": False, "accounts": 0}
    early = api.post(
        "/accounts/00000000-0000-0000-0000-000000000009/uploads",
        files={"file": fixture("hdfc_bank_sep.csv")},
    )
    assert early.status_code == 409 and early.json()["error"]["code"] == "SETUP_REQUIRED"
    assert early.json()["error"]["message"] == "Add an account first"
    assert api.post("/setup/complete").json()["error"]["code"] == "SETUP_REQUIRED"
    acc = api.post(
        "/accounts", json={"type": "savings", "institution": "HDFC Bank", "name": "HDFC Savings"}
    )
    assert acc.status_code == 201 and acc.json()["binding"] == "hdfc_bank"
    assert api.post("/setup/complete").status_code == 200
    assert api.get("/setup").json() == {"completed": True, "accounts": 1}
    r = api.post(
        f"/accounts/{acc.json()['id']}/uploads", files={"file": fixture("hdfc_bank_sep.csv")}
    )
    assert r.status_code == 200 and r.json()["rows_inserted"] == 9


def test_manual_account_needs_a_value_and_can_be_revalued(api: Any) -> None:
    bad = api.post("/accounts", json={"type": "fixed_deposit", "institution": "SBI", "name": "FD"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_INPUT"
    fd = api.post(
        "/accounts",
        json={
            "type": "fixed_deposit",
            "institution": "SBI",
            "name": "FD",
            "opening_value_paise": 50000000,
            "opening_date": "2026-04-01",
        },
    ).json()
    assert fd["manual"] is True and fd["binding"] is None
    assert api.post(
        f"/accounts/{fd['id']}/value", json={"as_of": "2026-09-30", "amount_paise": 51000000}
    ).json() == {"change": {"paise": 1000000, "formatted": "₹10,000.00"}}
    page = api.get(f"/accounts/{fd['id']}").json()
    assert page["account"]["balance"]["paise"] == 51000000


def test_edit_and_delete_account(api: Any) -> None:
    acc = api.post(
        "/accounts", json={"type": "credit_card", "institution": "HDFC Bank", "name": "Card"}
    ).json()
    assert (
        api.patch(f"/accounts/{acc['id']}", json={"name": "Millennia"}).json()["name"]
        == "Millennia"
    )
    assert api.get(f"/accounts/{acc['id']}/usage").json() == {"postings": 0, "imports": 0}
    assert api.delete(f"/accounts/{acc['id']}").status_code == 204
    assert api.get(f"/accounts/{acc['id']}").status_code == 404
