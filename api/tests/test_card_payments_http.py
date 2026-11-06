"""Paying a card from a bank row over HTTP: pick the card, see the books update, undo a wrong
pick, and let the card's own statement take over the payment."""

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


def waiting_payment(api: Any) -> dict[str, Any]:
    return next(
        i
        for i in api.get("/inbox").json()
        if i["kind"] == "unpaired" and i["amount"]["paise"] == 1626800
    )


def test_pick_a_card_then_undo_then_let_the_statement_match(api: Any) -> None:
    bank = add(api, "savings", "HDFC Bank", "HDFC")
    card = add(api, "credit_card", "HDFC Bank", "HDFC Card")
    other = add(api, "credit_card", "Axis Bank", "Axis Flipkart")
    up(api, bank, "hdfc_bank_sep.xls")
    item = waiting_payment(api)
    assert item["pay_card"] is True and item["amount"]["paise"] == 1626800
    tx = item["transaction_id"]

    options = api.get(f"/transactions/{tx}/card-options").json()
    assert options["amount"]["paise"] == 1626800
    assert {c["id"] for c in options["cards"]} == {card, other}
    assert all(c["current"] is False for c in options["cards"])

    paid = api.post(f"/transactions/{tx}/card-payment", json={"card_id": other}).json()
    assert paid["card"] == "Axis Flipkart" and paid["matched"] is False
    assert not any(
        i["kind"] == "unpaired" and i["amount"]["paise"] == 1626800
        for i in api.get("/inbox").json()
    )
    assert api.get(f"/accounts/{other}").json()["account"]["balance"]["paise"] == 1626800
    row = next(t for t in api.get("/transactions").json() if t["id"] == tx)
    assert row["card_payment"] == {"id": other, "name": "Axis Flipkart"} and row["editable"]
    for row in api.get("/transactions").json():
        assert sum(p["amount"]["paise"] for p in row["postings"]) == 0
    assert next(
        c for c in api.get(f"/transactions/{tx}/card-options").json()["cards"] if c["id"] == other
    )["current"]

    # a wrong pick is put back exactly, and the row waits for its other side again
    undone = api.post(f"/transactions/{tx}/card-payment/undo", json=paid["previous"])
    assert undone.status_code == 200
    assert waiting_payment(api)["transaction_id"] == tx
    assert api.get(f"/accounts/{other}").json()["account"]["balance"]["paise"] == 0

    # the right card, then its statement arrives and takes over the payment
    right = api.post(f"/transactions/{tx}/card-payment", json={"card_id": card}).json()
    assert up(api, card, "hdfc_card_sep.xlsx").json()["pairs_merged"] == 1
    stuck = api.post(f"/transactions/{tx}/card-payment/undo", json=right["previous"])
    assert stuck.status_code == 409
    assert api.get(f"/transactions/{tx}/card-options").json()["cards"] == []


def test_a_row_that_cannot_pay_a_card_offers_none_and_is_refused(api: Any) -> None:
    bank = add(api, "savings", "HDFC Bank", "HDFC")
    card = add(api, "credit_card", "HDFC Bank", "HDFC Card")
    up(api, bank, "hdfc_bank_sep.xls")
    credit = next(
        t
        for t in api.get("/transactions").json()
        if any(p["amount"]["paise"] == 15000000 for p in t["postings"])
    )
    assert api.get(f"/transactions/{credit['id']}/card-options").json()["cards"] == []
    refused = api.post(f"/transactions/{credit['id']}/card-payment", json={"card_id": card})
    assert refused.status_code in (400, 422)
    assert (
        api.get("/transactions/00000000-0000-0000-0000-000000000001/card-options").status_code
        == 404
    )
