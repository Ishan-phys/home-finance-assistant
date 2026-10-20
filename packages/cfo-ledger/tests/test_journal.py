"""Statement rows become balanced transactions; own-account halves pair (spec §5.3, §5.4, §5.9)."""

from __future__ import annotations

from datetime import date

import pytest
from cfo.core.chart import IN_TRANSIT, UNCATEGORIZED_IN, UNCATEGORIZED_OUT
from cfo.core.errors import InvalidInput, NotFoundError
from cfo.core.ids import new_id
from cfo.core.types import AccountType, MappingSource, MerchantMapping, Origin
from cfo.ledger.journal import RowIn, ignore, pair_in_transit, post_rows, recategorize
from cfo.ledger.repositories.accounts import AccountRepository, ImportRepository
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.transactions import JournalRepository, MappingRepository
from cfo.ledger.setup import AccountInput, add_account
from cfo.metrics.balances import balances_at
from sqlalchemy.orm import Session

D = date.fromisoformat
TODAY = D("2026-10-20")


def setup(s: Session):  # type: ignore[no-untyped-def]
    sav = add_account(
        s, AccountInput(AccountType.SAVINGS, "HDFC", "HDFC Savings"), TODAY, "hdfc_bank"
    )
    card = add_account(
        s, AccountInput(AccountType.CREDIT_CARD, "HDFC", "HDFC Card"), TODAY, "hdfc_card"
    )
    return sav, card


def statement(s: Session, account_id):  # type: ignore[no-untyped-def]
    return (
        ImportRepository(s)
        .add(
            account_id,
            "f.csv",
            "0" * 64,
            period_start=None,
            period_end=D("2026-09-30"),
            rows_inserted=0,
            hashes_ignored=0,
        )
        .id
    )


def row(day: str, amount: int, narration: str, h: str | None = None, own: bool = False) -> RowIn:
    return RowIn(
        D(day), amount, narration, narration.title(), h or f"{narration}{day}{amount}", own
    )


def path_of(s: Session, tx_id) -> dict[str, int]:  # type: ignore[no-untyped-def]
    t = JournalRepository(s).get(tx_id)
    accounts = {a.id: a.path for a in AccountRepository(s).list_all(include_retired=True)}
    return {accounts[p.account_id]: p.amount for p in t.postings}  # type: ignore[union-attr]


def test_rows_become_balanced_transactions(database: Database) -> None:
    with database.transaction() as s:
        sav, _ = setup(s)
        imp = statement(s, sav.id)
        mappings = {
            "NEFT CR SALARY": MerchantMapping(
                "NEFT CR SALARY", "Testcorp", "Income:Salary", MappingSource.MODEL
            ),
            "UPI SWIGGY": MerchantMapping(
                "UPI SWIGGY", "Swiggy", "Expenses:Food:Dining", MappingSource.MODEL
            ),
            "UPI FRIEND": MerchantMapping(
                "UPI FRIEND", "Personal transfer", "Expenses:People:Sent", MappingSource.MODEL
            ),
        }
        result = post_rows(
            s,
            sav,
            imp,
            [
                row("2026-09-01", 15000000, "NEFT CR SALARY"),
                row("2026-09-04", -1626800, "CC BILLPAY", own=True),
                row("2026-09-05", -64000, "UPI SWIGGY"),
                row("2026-09-06", -200000, "UPI FRIEND"),
                row("2026-09-07", -120000, "MYSTERY"),
                row("2026-09-08", 5000, "MYSTERY CREDIT"),
            ],
            mappings,
        )
        assert (result.inserted, result.ignored, result.uncategorized) == (6, 0, 2)
        txs = JournalRepository(s).list_all()
        assert all(sum(p.amount for p in t.postings) == 0 for t in txs)
        by_narration = {t.narration: t for t in txs}
        assert path_of(s, by_narration["NEFT CR SALARY"].id) == {
            sav.path: 15000000,
            "Income:Salary": -15000000,
        }
        assert path_of(s, by_narration["CC BILLPAY"].id)[IN_TRANSIT] == 1626800
        assert path_of(s, by_narration["MYSTERY"].id)[UNCATEGORIZED_OUT] == 120000
        assert path_of(s, by_narration["MYSTERY CREDIT"].id)[UNCATEGORIZED_IN] == -5000
        swiggy = by_narration["UPI SWIGGY"]
        assert swiggy.payee == "Swiggy" and swiggy.import_id == imp
        observed = next(p for p in swiggy.postings if p.origin is Origin.OBSERVED)
        assert observed.dedup_hash and observed.import_id == imp


def test_owner_mapping_wins_and_retired_targets_fall_back(database: Database) -> None:
    with database.transaction() as s:
        sav, _ = setup(s)
        imp = statement(s, sav.id)
        travel = AccountRepository(s).by_path("Expenses:Travel")
        AccountRepository(s).retire(travel.id, TODAY)  # type: ignore[union-attr]
        mappings = {
            "A": MerchantMapping("A", "A", "Expenses:Shopping", MappingSource.OWNER),
            "B": MerchantMapping("B", "B", "Expenses:Travel", MappingSource.MODEL),
            "C": MerchantMapping("C", "C", "Expenses:Gone", MappingSource.MODEL),
        }
        post_rows(
            s,
            sav,
            imp,
            [row("2026-09-01", -1, "A"), row("2026-09-01", -2, "B"), row("2026-09-01", -3, "C")],
            mappings,
        )
        by = {t.narration: t for t in JournalRepository(s).list_all()}
        a_counter = next(p for p in by["A"].postings if p.origin is not Origin.OBSERVED)
        assert a_counter.origin is Origin.INFERRED and "Expenses:Shopping" in path_of(s, by["A"].id)
        assert UNCATEGORIZED_OUT in path_of(s, by["B"].id)
        assert UNCATEGORIZED_OUT in path_of(s, by["C"].id)


def test_existing_hashes_are_skipped(database: Database) -> None:
    with database.transaction() as s:
        sav, _ = setup(s)
        imp = statement(s, sav.id)
        rows = [row("2026-09-01", -1, "A", h="h1"), row("2026-09-02", -2, "B", h="h2")]
        assert post_rows(s, sav, imp, rows, {}).inserted == 2
        again = post_rows(s, sav, imp, [*rows, row("2026-09-03", -3, "C", h="h3")], {})
        assert (again.inserted, again.ignored) == (1, 2)


def test_card_payment_pairs_across_statements(database: Database) -> None:
    with database.transaction() as s:
        sav, card = setup(s)
        post_rows(
            s, sav, statement(s, sav.id), [row("2026-09-04", -1626800, "CC BILLPAY", own=True)], {}
        )
        post_rows(
            s,
            card,
            statement(s, card.id),
            [row("2026-09-05", 1626800, "PAYMENT RECEIVED", own=True)],
            {},
        )
        assert pair_in_transit(s) == 1
        (merged,) = JournalRepository(s).list_all()
        assert path_of(s, merged.id) == {sav.path: -1626800, card.path: 1626800}
        transit = AccountRepository(s).by_path(IN_TRANSIT)
        assert balances_at(JournalRepository(s).list_all(), None).get(transit.id, 0) == 0  # type: ignore[union-attr]
        assert pair_in_transit(s) == 0


def test_recategorize_updates_same_narration_but_not_owner_choices(database: Database) -> None:
    with database.transaction() as s:
        sav, _ = setup(s)
        imp = statement(s, sav.id)
        post_rows(
            s,
            sav,
            imp,
            [
                row("2026-09-01", -100, "ZOMATO"),
                row("2026-09-08", -200, "ZOMATO"),
                row("2026-09-09", -300, "ZOMATO"),
            ],
            {},
        )
        first, second, third = JournalRepository(s).list_all()
        shopping = AccountRepository(s).by_path("Expenses:Shopping")
        dining = AccountRepository(s).by_path("Expenses:Food:Dining")
        assert recategorize(s, third.id, shopping.id) == 3  # type: ignore[union-attr]
        assert recategorize(s, first.id, dining.id) == 2  # type: ignore[union-attr]
        assert "Expenses:Food:Dining" in path_of(s, second.id)
        assert "Expenses:Shopping" in path_of(s, third.id)  # the owner's own choice stands
        assert MappingRepository(s).get_many(["ZOMATO"])["ZOMATO"].label == "Expenses:Food:Dining"


def test_recategorize_to_own_account_pairs_and_merged_cannot_be_recategorized(
    database: Database,
) -> None:
    with database.transaction() as s:
        sav, card = setup(s)
        post_rows(s, sav, statement(s, sav.id), [row("2026-09-04", -5000, "MYSTERY DEBIT")], {})
        post_rows(
            s, card, statement(s, card.id), [row("2026-09-04", 5000, "THANK YOU", own=True)], {}
        )
        mystery = next(t for t in JournalRepository(s).list_all() if t.narration == "MYSTERY DEBIT")
        transit = AccountRepository(s).by_path(IN_TRANSIT)
        recategorize(s, mystery.id, transit.id)  # type: ignore[union-attr]
        (merged,) = JournalRepository(s).list_all()
        with pytest.raises(InvalidInput):
            recategorize(s, merged.id, AccountRepository(s).by_path("Expenses:Fees").id)  # type: ignore[union-attr]
        with pytest.raises(InvalidInput):
            recategorize(s, merged.id, sav.id)


def test_ignored_row_does_not_return_on_reupload(database: Database) -> None:
    with database.transaction() as s:
        sav, _ = setup(s)
        imp = statement(s, sav.id)
        rows = [row("2026-09-01", -1, "DUP", h="dup")]
        post_rows(s, sav, imp, rows, {})
        (t,) = JournalRepository(s).list_all()
        ignore(s, t.id)
        assert JournalRepository(s).list_all() == []
        assert post_rows(s, sav, imp, rows, {}).inserted == 0
        with pytest.raises(NotFoundError):
            ignore(s, new_id())
