"""Removing a statement or an account keeps every transaction balanced (spec §5.10)."""

from __future__ import annotations

from datetime import date

from cfo.core.chart import IN_TRANSIT, OPENING
from cfo.core.types import AccountType
from cfo.ledger.journal import (
    RowIn,
    pair_in_transit,
    post_rows,
    recompute_opening,
    record_assertion,
    remove_import,
)
from cfo.ledger.repositories.accounts import (
    AccountRepository,
    AssertionRepository,
    ImportRepository,
)
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.ledger.setup import AccountInput, add_account, delete_account
from cfo.metrics.balances import balances_at
from sqlalchemy.orm import Session

D = date.fromisoformat
TODAY = D("2026-10-20")


def accounts(s: Session):  # type: ignore[no-untyped-def]
    sav = add_account(
        s, AccountInput(AccountType.SAVINGS, "HDFC", "HDFC Savings"), TODAY, "hdfc_bank"
    )
    card = add_account(
        s, AccountInput(AccountType.CREDIT_CARD, "HDFC", "HDFC Card"), TODAY, "hdfc_card"
    )
    return sav, card


def upload(s: Session, account, rows, closing: int | None = None):  # type: ignore[no-untyped-def]
    imp = ImportRepository(s).add(
        account.id,
        "f",
        "0" * 64,
        period_start=None,
        period_end=D("2026-09-30"),
        rows_inserted=len(rows),
        hashes_ignored=0,
    )
    post_rows(
        s, account, imp.id, [RowIn(D(d), a, n, n, f"{n}{d}{a}", own) for d, a, n, own in rows], {}
    )
    pair_in_transit(s)
    if closing is not None:
        record_assertion(s, account.id, D("2026-09-30"), closing, imp.id)
        recompute_opening(s, account.id)
    return imp


def balanced(s: Session) -> bool:
    return all(sum(p.amount for p in t.postings) == 0 for t in JournalRepository(s).list_all())


def test_remove_import_deletes_its_transactions_and_assertions(database: Database) -> None:
    with database.transaction() as s:
        sav, _ = accounts(s)
        imp = upload(s, sav, [("2026-09-03", -64000, "SWIGGY", False)], closing=100000)
        result = remove_import(s, imp.id)
        assert result.transactions_deleted == 2  # the row and the derived opening balance
        assert JournalRepository(s).list_all() == []
        assert AssertionRepository(s).list_all() == [] and ImportRepository(s).get(imp.id) is None


def test_remove_paired_import_rebalances_partner(database: Database) -> None:
    with database.transaction() as s:
        sav, card = accounts(s)
        upload(s, sav, [("2026-09-04", -1626800, "CC BILLPAY", True)])
        card_import = upload(s, card, [("2026-09-05", 1626800, "PAYMENT RECEIVED", True)])
        assert len(JournalRepository(s).list_all()) == 1  # merged
        result = remove_import(s, card_import.id)
        assert result.rebalanced == 1
        txs = JournalRepository(s).list_all()
        assert balanced(s) and len(txs) == 1
        transit = AccountRepository(s).by_path(IN_TRANSIT)
        assert balances_at(txs, D("2026-09-30"))[transit.id] == 1626800  # type: ignore[union-attr]
        # the savings half is waiting again, and pairs when the card statement returns
        upload(s, card, [("2026-09-05", 1626800, "PAYMENT RECEIVED", True)])
        assert len(JournalRepository(s).list_all()) == 1


def test_delete_account_removes_its_postings_and_keeps_books_balanced(database: Database) -> None:
    with database.transaction() as s:
        sav, card = accounts(s)
        upload(
            s,
            sav,
            [("2026-09-04", -1626800, "CC BILLPAY", True), ("2026-09-06", -500, "TEA", False)],
            closing=10000,
        )
        upload(s, card, [("2026-09-05", 1626800, "PAYMENT RECEIVED", True)])
        delete_account(s, card.id)
        assert AccountRepository(s).get(card.id) is None
        assert balanced(s)
        txs = JournalRepository(s).list_all()
        opening = AccountRepository(s).by_path(OPENING)
        assert {t.narration for t in txs} == {"CC BILLPAY", "TEA", "Opening balance"}
        assert opening is not None


def test_remove_the_debit_side_of_a_paired_transfer_keeps_the_credit_side(
    database: Database,
) -> None:
    with database.transaction() as s:  # final review C1
        sav, card = accounts(s)
        sav_import = upload(s, sav, [("2026-09-04", -1626800, "CC BILLPAY", True)])
        upload(s, card, [("2026-09-05", 1626800, "PAYMENT RECEIVED", True)])
        remove_import(s, sav_import.id)
        txs = JournalRepository(s).list_all()
        assert balanced(s) and len(txs) == 1
        (kept,) = txs
        assert {p.account_id for p in kept.postings} == {
            card.id,
            AccountRepository(s).by_path(IN_TRANSIT).id,
        }  # type: ignore[union-attr]
        # the card half waits again, and pairs when the savings statement returns
        upload(s, sav, [("2026-09-04", -1626800, "CC BILLPAY", True)])
        assert len(JournalRepository(s).list_all()) == 1


def test_delete_the_debit_side_account_of_a_paired_transfer(database: Database) -> None:
    with database.transaction() as s:  # final review C1
        sav, card = accounts(s)
        upload(s, sav, [("2026-09-04", -1626800, "CC BILLPAY", True)], closing=10000)
        upload(s, card, [("2026-09-05", 1626800, "PAYMENT RECEIVED", True)])
        delete_account(s, sav.id)
        assert AccountRepository(s).get(sav.id) is None and balanced(s)
        (kept,) = JournalRepository(s).list_all()
        transit = AccountRepository(s).by_path(IN_TRANSIT)
        assert {p.account_id for p in kept.postings} == {card.id, transit.id}  # type: ignore[union-attr]
