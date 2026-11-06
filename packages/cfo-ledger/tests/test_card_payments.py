"""Paying a card from a bank row: the books balance at every step, the card's own statement line
replaces the recorded payment, and a mistaken pick can be put back (the AI CFO card-payment flow)."""

from __future__ import annotations

from datetime import date

import pytest
from cfo.core.chart import IN_TRANSIT, UNCATEGORIZED_OUT
from cfo.core.errors import ConflictError, InvalidInput
from cfo.core.types import Account, AccountType, Origin
from cfo.ledger.card_payments import pay_card, undo_card_payment
from cfo.ledger.journal import RowIn, pair_in_transit, post_rows, remove_import
from cfo.ledger.repositories.accounts import AccountRepository, ImportRepository
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.ledger.setup import AccountInput, add_account
from cfo.metrics.balances import balances_at
from sqlalchemy.orm import Session

D = date.fromisoformat
TODAY = D("2026-11-06")


def accounts(s: Session) -> tuple[Account, Account, Account]:
    sav = add_account(
        s, AccountInput(AccountType.SAVINGS, "HDFC Bank", "HDFC Salary"), TODAY, "hdfc_bank"
    )
    axis = add_account(
        s, AccountInput(AccountType.CREDIT_CARD, "Axis Bank", "Axis Flipkart"), TODAY, "axis"
    )
    swiggy = add_account(
        s, AccountInput(AccountType.CREDIT_CARD, "HDFC Bank", "HDFC Swiggy"), TODAY, "hdfc_card"
    )
    return sav, axis, swiggy


def statement(s: Session, account: Account, name: str = "f"):  # type: ignore[no-untyped-def]
    return (
        ImportRepository(s)
        .add(
            account.id,
            name,
            "0" * 64,
            period_start=None,
            period_end=D("2026-11-10"),
            rows_inserted=0,
            hashes_ignored=0,
        )
        .id
    )


def bank_debit(s: Session, sav: Account, day: str, paise: int, text: str = "PAYMENT ON CRED"):  # type: ignore[no-untyped-def]
    """A debit on the bank account whose other side is still a guess (uncategorized)."""
    post_rows(s, sav, statement(s, sav, f"{day}{paise}"), [_row(day, -paise, text)], {})
    return next(
        t
        for t in JournalRepository(s).list_all([sav.id])
        if t.date == D(day) and any(p.amount == -paise for p in t.postings)
    )


def card_line(s: Session, card: Account, day: str, paise: int, h: str = "") -> None:
    """The card statement's own line for a payment: money in, other side money in transit."""
    post_rows(
        s,
        card,
        statement(s, card, f"{card.display_name}{day}{paise}{h}"),
        [_row(day, paise, "PAYMENT RECEIVED", own=True, h=h)],
        {},
    )


def _row(day: str, amount: int, text: str, own: bool = False, h: str = "") -> RowIn:
    return RowIn(D(day), amount, text, text.title(), f"{text}{day}{amount}{h}", own)


def legs(s: Session, tx_id) -> dict[str, tuple[int, Origin]]:  # type: ignore[no-untyped-def]
    t = JournalRepository(s).get(tx_id)
    paths = {a.id: a.path for a in AccountRepository(s).list_all(include_retired=True)}
    return {paths[p.account_id]: (p.amount, p.origin) for p in t.postings}  # type: ignore[union-attr]


def balanced(s: Session) -> bool:
    return all(sum(p.amount for p in t.postings) == 0 for t in JournalRepository(s).list_all())


def test_paying_a_card_moves_the_other_side_to_the_card_and_balances(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, _ = accounts(s)
        tx = bank_debit(s, sav, "2026-10-30", 1211186)
        result = pay_card(s, tx.id, axis.id)
        assert not result.matched
        assert (result.previous.account_id, result.previous.origin) == (
            AccountRepository(s).by_path(UNCATEGORIZED_OUT).id,  # type: ignore[union-attr]
            Origin.INFERRED,
        )
        assert legs(s, tx.id) == {
            sav.path: (-1211186, Origin.OBSERVED),
            axis.path: (1211186, Origin.OWNER),
        }
        assert balanced(s)
        assert balances_at(JournalRepository(s).list_all())[axis.id] == 1211186


def test_the_cards_statement_line_replaces_the_recorded_payment(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, _ = accounts(s)
        tx = bank_debit(s, sav, "2026-10-30", 1211186)
        pay_card(s, tx.id, axis.id)
        before = balances_at(JournalRepository(s).list_all())
        card_line(s, axis, "2026-10-31", 1211186)
        pair_in_transit(s)
        txs = JournalRepository(s).list_all()
        assert len(txs) == 1 and balanced(s)
        assert legs(s, txs[0].id) == {
            sav.path: (-1211186, Origin.OBSERVED),
            axis.path: (1211186, Origin.OBSERVED),
        }
        assert balances_at(txs)[axis.id] == before[axis.id]  # the swap changes no balance


def test_a_statement_that_was_uploaded_first_matches_at_once(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, _ = accounts(s)
        card_line(s, axis, "2026-10-31", 1211186)
        tx = bank_debit(s, sav, "2026-10-30", 1211186)
        assert pay_card(s, tx.id, axis.id).matched
        assert len(JournalRepository(s).list_all()) == 1 and balanced(s)


def test_the_same_amount_on_two_cards_matches_only_the_card_picked(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, swiggy = accounts(s)
        tx = bank_debit(s, sav, "2026-10-30", 612900)
        pay_card(s, tx.id, swiggy.id)
        card_line(s, axis, "2026-10-30", 612900)  # a different card's payment line
        pair_in_transit(s)
        assert legs(s, tx.id)[swiggy.path][1] is Origin.OWNER  # untouched, still waiting
        card_line(s, swiggy, "2026-10-31", 612900)
        pair_in_transit(s)
        assert legs(s, tx.id)[swiggy.path][1] is Origin.OBSERVED
        left = [t for t in JournalRepository(s).list_all() if t.id != tx.id]
        assert len(left) == 1 and legs(s, left[0].id)[IN_TRANSIT][0] == -612900  # axis line waits
        assert balanced(s)


def test_equal_payments_to_one_card_match_one_to_one_by_closest_date(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, _ = accounts(s)
        early = bank_debit(s, sav, "2026-10-20", 260800)
        late = bank_debit(s, sav, "2026-10-29", 260800)
        pay_card(s, early.id, axis.id)
        pay_card(s, late.id, axis.id)
        card_line(s, axis, "2026-10-30", 260800, "a")
        pair_in_transit(s)
        assert legs(s, late.id)[axis.path][1] is Origin.OBSERVED  # the nearer date wins
        assert legs(s, early.id)[axis.path][1] is Origin.OWNER  # the other keeps waiting
        card_line(s, axis, "2026-10-21", 260800, "b")
        pair_in_transit(s)
        assert legs(s, early.id)[axis.path][1] is Origin.OBSERVED
        assert len(JournalRepository(s).list_all()) == 2 and balanced(s)


def test_a_different_amount_is_never_matched(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, _ = accounts(s)
        tx = bank_debit(s, sav, "2026-10-30", 1000000)
        pay_card(s, tx.id, axis.id)
        card_line(s, axis, "2026-10-30", 1211186)
        pair_in_transit(s)
        assert legs(s, tx.id)[axis.path][1] is Origin.OWNER
        assert len(JournalRepository(s).list_all()) == 2 and balanced(s)


def test_a_wrong_card_can_be_changed_and_a_mistake_put_back(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, swiggy = accounts(s)
        tx = bank_debit(s, sav, "2026-10-30", 612900)
        first = pay_card(s, tx.id, axis.id)
        second = pay_card(s, tx.id, swiggy.id)  # the owner noticed and picked the right card
        assert second.previous.account_id == axis.id and second.previous.origin is Origin.OWNER
        assert swiggy.path in legs(s, tx.id) and axis.path not in legs(s, tx.id)
        undo_card_payment(s, tx.id, first.previous.account_id, first.previous.origin)
        assert legs(s, tx.id)[UNCATEGORIZED_OUT] == (612900, Origin.INFERRED)
        assert balanced(s)


def test_undo_to_money_in_transit_pairs_again(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, _ = accounts(s)
        post_rows(
            s, sav, statement(s, sav), [_row("2026-10-30", -500000, "CC BILLPAY", own=True)], {}
        )
        tx = JournalRepository(s).list_all([sav.id])[0]
        result = pay_card(s, tx.id, axis.id)
        card_line(s, axis, "2026-12-31", 500000)  # too far away to match
        undo_card_payment(s, tx.id, result.previous.account_id, result.previous.origin)
        assert legs(s, tx.id)[IN_TRANSIT] == (500000, Origin.INFERRED)
        assert balanced(s)


def test_a_matched_payment_cannot_be_undone(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, _ = accounts(s)
        tx = bank_debit(s, sav, "2026-10-30", 1211186)
        result = pay_card(s, tx.id, axis.id)
        card_line(s, axis, "2026-10-31", 1211186)
        pair_in_transit(s)
        with pytest.raises(ConflictError):
            undo_card_payment(s, tx.id, result.previous.account_id, result.previous.origin)


def test_only_bank_money_going_out_can_pay_a_card(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, swiggy = accounts(s)
        post_rows(s, sav, statement(s, sav), [_row("2026-10-01", 500000, "SALARY")], {})
        credit = JournalRepository(s).list_all([sav.id])[0]
        with pytest.raises(InvalidInput):
            pay_card(s, credit.id, axis.id)  # money in is not a payment
        debit = bank_debit(s, sav, "2026-10-30", 100)
        with pytest.raises(InvalidInput):
            pay_card(s, debit.id, sav.id)  # not a card
        AccountRepository(s).retire(swiggy.id, TODAY)
        with pytest.raises(InvalidInput):
            pay_card(s, debit.id, swiggy.id)  # a retired card


def test_removing_the_bank_statement_drops_a_recorded_payment(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, _ = accounts(s)
        tx = bank_debit(s, sav, "2026-10-30", 1211186)
        pay_card(s, tx.id, axis.id)
        imp = JournalRepository(s).get(tx.id).import_id  # type: ignore[union-attr]
        remove_import(s, imp)  # type: ignore[arg-type]
        assert JournalRepository(s).list_all() == [] and balanced(s)


def test_removing_the_card_statement_sends_the_payment_back_to_transit(database: Database) -> None:
    with database.transaction() as s:
        sav, axis, _ = accounts(s)
        tx = bank_debit(s, sav, "2026-10-30", 1211186)
        pay_card(s, tx.id, axis.id)
        card_line(s, axis, "2026-10-31", 1211186)
        pair_in_transit(s)
        card_import = ImportRepository(s).list_all(axis.id)[0]
        remove_import(s, card_import.id)
        assert legs(s, tx.id) == {
            sav.path: (-1211186, Origin.OBSERVED),
            IN_TRANSIT: (1211186, Origin.INFERRED),
        }
        assert balanced(s)
