"""Owner rules over HTTP (spec 2)."""

from __future__ import annotations

from typing import Any

from cfo.testing import FIXTURE_DIR


def upload(api: Any) -> str:
    acc = api.post(
        "/accounts", json={"type": "savings", "institution": "HDFC Bank", "name": "HDFC"}
    ).json()
    api.post(
        f"/accounts/{acc['id']}/uploads",
        files={"file": ("s.xls", (FIXTURE_DIR / "hdfc_bank_sep.xls").read_bytes())},
    )
    return acc["id"]


def category(api: Any, name: str) -> str:
    cats = api.get("/categories").json()
    return next(c["id"] for c in cats["out"] + cats["in"] if c["name"] == name)


def test_create_list_edit_reorder_delete(api: Any) -> None:
    upload(api)
    health = category(api, "Health")
    a = api.post("/rules", json={"match_text": "pharmacy", "target_id": health})
    b = api.post("/rules", json={"match_text": "clinic", "target_id": health, "way": "debit"})
    assert a.status_code == 201 and b.status_code == 201
    ids = [x["id"] for x in api.get("/rules").json()]
    assert api.post("/rules/reorder", json={"ids": ids[::-1]}).json()[0]["id"] == ids[-1]
    edited = api.patch(f"/rules/{a.json()['id']}", json={"label": "Chemist"}).json()
    assert edited["label"] == "Chemist" and edited["target"]["name"] == "Health"
    assert api.delete(f"/rules/{b.json()['id']}").status_code == 204
    assert len(api.get("/rules").json()) == 1


def test_blank_text_and_bad_target_are_rejected(api: Any) -> None:
    upload(api)
    health = category(api, "Health")
    assert api.post("/rules", json={"match_text": "  ", "target_id": health}).status_code == 422
    real = api.get("/accounts").json()
    assert real, "setup should leave a real account"
    account_id = real[0]["id"] if isinstance(real, list) else real["accounts"][0]["id"]
    bad = api.post("/rules", json={"match_text": "x", "target_id": account_id})
    assert bad.status_code in (400, 422)


def test_preview_then_apply_moves_matching_rows(api: Any) -> None:
    upload(api)
    health = category(api, "Health")
    body = {"match_text": "GROCER", "target_id": health}
    matches = api.post("/rules/preview", json=body).json()["matches"]
    assert matches >= 1
    made = api.post("/rules", json={**body, "apply_now": True}).json()
    assert made["applied"] == matches
    rows = api.get("/transactions", params={"q": "GROCER"}).json()
    assert rows and all(r["category"]["name"] == "Health" for r in rows)
