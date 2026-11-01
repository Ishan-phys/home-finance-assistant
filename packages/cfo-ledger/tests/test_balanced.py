"""Double entry is enforced by the system: every transaction's postings sum to zero (spec 5)."""

from __future__ import annotations

from datetime import date

import pytest
from cfo.core.chart import IN_TRANSIT, UNCATEGORIZED_OUT
from cfo.core.errors import UnbalancedTransaction
from cfo.core.ids import new_id
from cfo.core.types import AccountType, Origin, Posting, Transaction
from cfo.ledger.journal import RowIn, pair_in_transit, post_rows, recategorize
from cfo.ledger.repositories.accounts import AccountRepository, ImportRepository
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.ledger.setup import AccountInput, add_account
from cfo.ledger.verify import verify_books
from sqlalchemy.exc import DBAPIError

TODAY = date(2026, 10, 20)


def setup(s):  # type: ignore[no-untyped-def]
    sav = add_account(
        s, AccountInput(AccountType.SAVINGS, "HDFC", "HDFC Savings"), TODAY, "hdfc_bank"
    )
    card = add_account(
        s, AccountInput(AccountType.CREDIT_CARD, "HDFC", "HDFC Card"), TODAY, "hdfc_card"
    )
    return sav, card


def statement(s, account_id):  # type: ignore[no-untyped-def]
    return (
        ImportRepository(s)
        .add(
            account_id,
            "f.csv",
            "0" * 64,
            period_start=None,
            period_end=date(2026, 9, 30),
            rows_inserted=0,
            hashes_ignored=0,
        )
        .id
    )


def row(day: str, amount: int, narration: str, h: str) -> RowIn:
    return RowIn(date.fromisoformat(day), amount, narration, narration.title(), h)


def _tx(a, b, amount_a: int, amount_b: int) -> Transaction:  # type: ignore[no-untyped-def]
    return Transaction(
        new_id(),
        date(2026, 9, 1),
        "n",
        "p",
        (
            Posting(a.id, amount_a, Origin.OBSERVED),
            Posting(b.id, amount_b, Origin.INFERRED),
        ),
    )


def test_unbalanced_transaction_cannot_be_built(database) -> None:  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        sav, _ = setup(s)
        other = AccountRepository(s).by_path(UNCATEGORIZED_OUT)
        with pytest.raises(UnbalancedTransaction):
            _tx(sav, other, -100, 90)


def test_unbalanced_commit_fails(database) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(DBAPIError, match="does not balance"):
        with database.transaction() as s:
            sav, _ = setup(s)
            other = AccountRepository(s).by_path(UNCATEGORIZED_OUT)
            tx = JournalRepository(s).add(_tx(sav, other, -100, 100))
            JournalRepository(s).add_posting(tx.id, Posting(other.id, 5, Origin.INFERRED))


def test_verify_books_empty_after_upload_pair_and_recategorize(database) -> None:  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        sav, card = setup(s)
        post_rows(
            s, sav, statement(s, sav.id),
            [row("2026-09-02", -500000, "CRED PAYMENT", "h1"), row("2026-09-03", -1200, "SHOP", "h2")],
            {},
        )  # fmt: skip
        post_rows(
            s,
            card,
            statement(s, card.id),
            [row("2026-09-03", 500000, "PAYMENT RECEIVED", "h3")],
            {},
        )
        transit = AccountRepository(s).by_path(IN_TRANSIT)
        for t in JournalRepository(s).list_all([sav.id]):
            if t.narration == "CRED PAYMENT":
                recategorize(s, t.id, transit.id)
        for t in JournalRepository(s).list_all([card.id]):
            recategorize(s, t.id, transit.id)
        pair_in_transit(s)
        assert verify_books(s) == []
