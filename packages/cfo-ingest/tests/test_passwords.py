"""Password-protected statements: PDFs and Office-encrypted workbooks."""

from __future__ import annotations

import io
from datetime import date

import msoffcrypto
import pikepdf
import pytest
from cfo.core.types import AccountType
from cfo.ingest.upload import upload_statement
from cfo.ledger.repositories.accounts import ImportRepository
from cfo.ledger.repositories.db import Database
from cfo.parse.base import PasswordInvalid, PasswordRequired
from cfo.parse.unlock import unlock
from cfo.testing import FIXTURE_DIR, SeedClient

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


# the unlock layer -----------------------------------------------------------------


@pytest.mark.parametrize("make", [protected_pdf, protected_xlsx], ids=["pdf", "xlsx"])
def test_unlock_requires_then_accepts_the_right_password(make) -> None:  # type: ignore[no-untyped-def]
    locked = make(SECRET)
    with pytest.raises(PasswordRequired):
        unlock(locked, None)
    with pytest.raises(PasswordRequired):
        unlock(locked, "")
    with pytest.raises(PasswordInvalid):
        unlock(locked, "wrong")
    plain = unlock(locked, SECRET)
    assert plain != locked


def test_unprotected_files_pass_through_with_or_without_a_password() -> None:
    for name in (
        "axis_card_sep.pdf",
        "sbi_bank_sep.xlsx",
        "hdfc_bank_sep.xls",
        "hdfc_card_sep.xlsx",
    ):
        data = (FIXTURE_DIR / name).read_bytes()
        assert unlock(data, None) == data and unlock(data, "ignored") == data, name


def test_errors_never_echo_the_password() -> None:
    for make in (protected_pdf, protected_xlsx):
        with pytest.raises(PasswordInvalid) as err:
            unlock(make(SECRET), "my-guess-123")
        assert "my-guess-123" not in str(err.value) and SECRET not in str(err.value)


# through the upload pipeline ---------------------------------------------------------


def make_account(database: Database, type: AccountType, binding: str) -> object:
    from cfo.ledger.setup import AccountInput, add_account

    with database.transaction() as s:
        return add_account(s, AccountInput(type, "Bank", f"A {binding}"), TODAY, binding).id


def test_protected_pdf_and_workbook_import_once_unlocked(database: Database) -> None:
    axis = make_account(database, AccountType.CREDIT_CARD, "axis_credit_card")
    sbi = make_account(database, AccountType.SAVINGS, "sbi_bank")
    cases = [
        (axis, "axis.pdf", protected_pdf(SECRET), 5),
        (sbi, "sbi.xlsx", protected_xlsx(SECRET), 4),
    ]
    for account, name, content, rows in cases:
        with pytest.raises(PasswordRequired):
            upload_statement(database, account, name, content, SeedClient(), TODAY)
        with pytest.raises(PasswordInvalid):
            upload_statement(database, account, name, content, SeedClient(), TODAY, "nope")
        r = upload_statement(database, account, name, content, SeedClient(), TODAY, SECRET)
        assert r.rows_inserted == rows
        again = upload_statement(database, account, name, content, SeedClient(), TODAY, SECRET)
        assert again.rows_inserted == 0  # dedup is unaffected by the encryption


def test_failed_unlock_writes_nothing(database: Database) -> None:
    axis = make_account(database, AccountType.CREDIT_CARD, "axis_credit_card")
    with pytest.raises(PasswordInvalid):
        upload_statement(database, axis, "a.pdf", protected_pdf(SECRET), SeedClient(), TODAY, "bad")
    with database.transaction() as s:
        assert ImportRepository(s).list_all() == []
