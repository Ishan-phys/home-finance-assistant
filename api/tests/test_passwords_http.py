"""Password-protected statements: PDFs and Office-encrypted workbooks."""

from __future__ import annotations

import io
from datetime import date

import msoffcrypto
import pikepdf
from cfo.api.app import create_app
from cfo.ledger.repositories.db import Database
from cfo.testing import FIXTURE_DIR, SeedClient
from cfo.testing.api import person_client

TODAY = date(2026, 10, 3)
SECRET = "Pa55-w0rd"


def protected_pdf(password: str) -> bytes:
    out = io.BytesIO()
    with pikepdf.open(FIXTURE_DIR / "axis_card_sep.pdf") as pdf:
        pdf.save(
            out, encryption=pikepdf.Encryption(user=password, owner="owner-" + password, aes=True)
        )
    return out.getvalue()


def protected_xlsx(password: str) -> bytes:
    out = io.BytesIO()
    with open(FIXTURE_DIR / "sbi_bank_sep.xlsx", "rb") as f:
        msoffcrypto.OfficeFile(f).encrypt(password, out)
    return out.getvalue()


# over HTTP ----------------------------------------------------------------------------


def test_http_codes_and_form_password(database: Database) -> None:
    api = person_client(database, create_app(db=database, client=SeedClient(), clock=lambda: TODAY))
    acc = api.post(
        "/accounts",
        json={"type": "credit_card", "institution": "Axis Bank", "name": "Axis"},
    ).json()["id"]
    locked = protected_pdf(SECRET)

    def send(password: str | None):  # type: ignore[no-untyped-def]
        return api.post(
            f"/accounts/{acc}/uploads",
            files={"file": ("axis.pdf", locked)},
            data={} if password is None else {"password": password},
        )

    missing = send(None)
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "PASSWORD_REQUIRED"
    wrong = send("nope")
    assert wrong.json()["error"]["code"] == "PASSWORD_INVALID" and "nope" not in wrong.text
    ok = send(SECRET)
    assert ok.status_code == 200 and ok.json()["rows_inserted"] == 5
    assert SECRET not in str(
        api.get(f"/accounts/{acc}").json()
    )  # nothing about the password is kept
