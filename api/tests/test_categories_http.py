"""The owner's own categories (spec §3, D8)."""

from __future__ import annotations

from typing import Any

from cfo.testing import FIXTURE_DIR


def setup_with_statement(api: Any) -> str:
    acc = api.post(
        "/accounts", json={"type": "savings", "institution": "HDFC Bank", "name": "HDFC"}
    ).json()
    api.post(
        f"/accounts/{acc['id']}/uploads",
        files={"file": ("s.xls", (FIXTURE_DIR / "hdfc_bank_sep.xls").read_bytes())},
    )
    return acc["id"]


def test_defaults_are_listed_with_descriptions(api: Any) -> None:
    cats = api.get("/categories").json()
    assert {c["name"] for c in cats["in"]} >= {"Salary", "Interest", "Rewards"}
    dining = next(c for c in cats["out"] if c["name"] == "Dining")
    assert (
        dining["description"] == "Restaurants, cafés, food delivery" and dining["default"] is True
    )


def test_add_custom_category_and_recategorize(api: Any) -> None:
    setup_with_statement(api)
    gym = api.post(
        "/categories", json={"name": "Gym", "direction": "out", "description": "Memberships"}
    )
    assert gym.status_code == 201
    rows = api.get("/transactions", params={"q": "GROCER"}).json()
    r = api.patch(f"/transactions/{rows[0]['id']}/category", json={"account_id": gym.json()["id"]})
    assert r.status_code == 200 and r.json()["changed"] >= 1
    again = api.get("/transactions", params={"q": "GROCER"}).json()
    assert again[0]["category"]["name"] == "Gym"
    assert (
        api.patch(
            f"/categories/{gym.json()['id']}", json={"description": "Gyms and studios"}
        ).json()["description"]
        == "Gyms and studios"
    )
    blank = api.post("/categories", json={"name": "Pets", "direction": "out", "description": " "})
    assert blank.status_code == 422


def test_category_in_use_cannot_be_deleted_but_can_be_merged(api: Any) -> None:
    setup_with_statement(api)
    cats = api.get("/categories").json()["out"]
    housing = next(c for c in cats if c["name"] == "Housing")
    health = next(c for c in cats if c["name"] == "Health")
    r = api.delete(f"/categories/{housing['id']}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CATEGORY_IN_USE"
    assert r.json()["error"]["hint"] == "Merge it into another category instead."
    merged = api.post(f"/categories/{housing['id']}/merge", json={"into_id": health["id"]}).json()
    assert merged == {"moved": 1}
    after = {c["name"]: c for c in api.get("/categories").json()["out"]}
    assert after["Housing"]["retired"] is True
