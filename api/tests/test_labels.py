from __future__ import annotations

import io
from datetime import date

import openpyxl
import pytest
from cfo.api.app import create_app
from cfo.core.errors import RedactionFailed  # noqa: F401
from cfo.ledger.repositories.db import Database
from cfo.testing import SeedClient
from cfo.testing.api import PersonClient, person_client

TODAY = date(2026, 10, 3)


def workbook() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in [
        ["Statement From  :  01/09/2026         To  :  30/09/2026"],
        ["Date", "Narration", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
        ["********"] * 5,
        [
            "02/09/26",
            "UPI-TARA NAIR-tara.n@okhdfc-IDFB0040101-412345678901-Rent",
            5000.0,
            None,
            95000.0,
        ],
        ["03/09/26", "UPI-SWIGGY-swiggy@icici-ICIC0000001-1-Order", 250.0, None, 94750.0],
    ]:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.fixture
def api(database: Database) -> PersonClient:
    return person_client(
        database,
        create_app(db=database, client=SeedClient(), clock=lambda: TODAY),
        raise_server_exceptions=False,
    )


def test_upload_reports_what_was_redacted_and_labels_show_only_in_the_cockpit(
    api: PersonClient,
) -> None:
    acc = api.post(
        "/accounts", json={"type": "savings", "institution": "HDFC Bank", "name": "HDFC"}
    ).json()["id"]
    r = api.post(f"/accounts/{acc}/uploads", files={"file": ("s.xlsx", workbook())})
    assert r.status_code == 200
    redaction = r.json()["redaction"]
    assert (
        redaction["PERSON"] >= 1 and redaction["VPA"] >= 1 and "tara" not in str(r.json()).lower()
    )

    tokens = api.get("/privacy/labels").json()
    person = next(t for t in tokens if t["token"].startswith("[PERSON:"))
    assert person["label"] is None and person["count"] == 1

    # before labelling, the cockpit shows a readable stand-in, never the real name
    rows = api.get("/transactions").json()
    assert any("Person " in t["narration"] for t in rows)
    assert "TARA" not in str(rows).upper()

    # label it, and the cockpit shows the label
    assert (
        api.put("/privacy/labels", json={"token": person["token"], "label": "Landlord"}).status_code
        == 200
    )
    rows = api.get("/transactions").json()
    assert any("Landlord" in t["narration"] for t in rows)
    inbox = api.get("/inbox").json()
    assert "TARA" not in str(inbox).upper()

    # the stored value, the tokens endpoint and so anything a model could see stay token-only
    by_token = {t["token"]: t["label"] for t in api.get("/privacy/labels").json()}
    assert by_token[person["token"]] == "Landlord"
    # clearing the label restores the stand-in
    api.put("/privacy/labels", json={"token": person["token"], "label": "  "})
    by_token = {t["token"]: t["label"] for t in api.get("/privacy/labels").json()}
    assert by_token[person["token"]] is None


def test_label_input_is_validated(api: PersonClient) -> None:
    assert (
        api.put("/privacy/labels", json={"token": "not a token", "label": "x"}).status_code == 422
    )
    assert (
        api.put("/privacy/labels", json={"token": "[PERSON:ab12]", "label": "x" * 200}).status_code
        == 422
    )


def test_a_redaction_failure_is_a_422_and_imports_nothing(
    api: PersonClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cfo.redact.redactor as module

    def boom(self, text):  # type: ignore[no-untyped-def]
        raise ValueError("kaboom")

    monkeypatch.setattr(module._Run, "scrub", boom)
    acc = api.post(
        "/accounts", json={"type": "savings", "institution": "HDFC Bank", "name": "HDFC"}
    ).json()["id"]
    r = api.post(f"/accounts/{acc}/uploads", files={"file": ("s.xlsx", workbook())})
    assert r.status_code == 422 and r.json()["error"]["code"] == "REDACTION_FAILED"
    assert api.get(f"/accounts/{acc}").json()["statements"] == []
    assert api.get("/transactions").json() == []
