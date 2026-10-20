"""Reports and statement removal over HTTP."""

from __future__ import annotations

from typing import Any

from cfo.testing import FIXTURE_DIR


def add(api: Any, type: str, institution: str, name: str) -> str:
    return api.post(
        "/accounts", json={"type": type, "institution": institution, "name": name}
    ).json()["id"]


def up(api: Any, account: str, name: str) -> Any:
    return api.post(
        f"/accounts/{account}/uploads", files={"file": (name, (FIXTURE_DIR / name).read_bytes())}
    )


def test_remove_statement_keeps_books_balanced(api: Any) -> None:
    bank, card = (
        add(api, "savings", "HDFC Bank", "HDFC"),
        add(api, "credit_card", "HDFC Bank", "Card"),
    )
    up(api, bank, "hdfc_bank_sep.xls")
    card_import = up(api, card, "hdfc_card_sep.xlsx").json()
    assert card_import["pairs_merged"] == 1
    statements = api.get(f"/accounts/{card}").json()["statements"]
    assert [s["import_id"] for s in statements] == [card_import["import_id"]]
    assert api.delete(f"/imports/{card_import['import_id']}").status_code == 200
    for row in api.get("/transactions").json():
        assert sum(p["amount"]["paise"] for p in row["postings"]) == 0
    assert any(i["kind"] == "unpaired" for i in api.get("/inbox").json())


def test_reports_respond_with_plain_json(api: Any) -> None:
    bank = add(api, "savings", "HDFC Bank", "HDFC")
    up(api, bank, "hdfc_bank_sep.xls")
    # the bill payment and SIP wait in transit until their other sides are uploaded
    assert api.get("/reports/overview").json()["net_worth"]["total"]["paise"] == 19245550 + 2626800
    assert api.get("/reports/balance-sheet").json()["groups"][0]["label"] == "Cash and savings"
    month = api.get("/reports/income-statement", params={"month": "2026-09"}).json()
    assert month["check"]["ok"] is True and month["earned"]["paise"] == 15000000
    assert api.get("/reports/safe-to-spend").json()["amount"]["paise"] == 19245550
    assert api.get("/reports/leaks", params={"month": "2026-09"}).status_code == 200
    assert api.get("/accounts/tree").json()["kinds"][0]["label"] == "Assets"
    bad = api.get("/reports/income-statement", params={"month": "Sept"})
    assert bad.status_code == 422


def test_settings_round_trip_and_safe_to_spend(api: Any) -> None:
    bank = add(api, "savings", "HDFC Bank", "HDFC")
    up(api, bank, "hdfc_bank_sep.xls")
    r = api.patch(
        "/settings", json={"min_cash_buffer_paise": 5000000, "monthly_allowance_paise": 100000}
    )
    assert r.json()["monthly_allowance"]["paise"] == 100000
    sts = api.get("/reports/safe-to-spend").json()
    assert sts["kept_aside"]["paise"] == 5000000 and sts["amount"]["paise"] <= 100000
    cleared = api.patch("/settings", json={"monthly_allowance_paise": None}).json()
    assert cleared["monthly_allowance"] is None


def test_ignore_a_row(api: Any) -> None:
    bank = add(api, "savings", "HDFC Bank", "HDFC")
    up(api, bank, "hdfc_bank_sep.xls")
    cafe = [
        r
        for r in api.get("/transactions", params={"q": "TEST CAFE"}).json()
        if r["amount"]["paise"] == 25000
    ]
    assert api.post(f"/transactions/{cafe[0]['id']}/ignore").status_code == 200
    assert len(api.get("/transactions", params={"q": "TEST CAFE-"}).json()) == len(cafe) - 1
    assert up(api, bank, "hdfc_bank_sep.xls").json()["rows_inserted"] == 0
