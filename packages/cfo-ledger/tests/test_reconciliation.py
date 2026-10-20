"""Balance assertions, the derived opening balance, and revaluation (spec §5.5, §5.7, §5.8)."""

from __future__ import annotations

from datetime import date

import pytest
from cfo.core.chart import OPENING, REVALUATION
from cfo.core.errors import InvalidInput
from cfo.core.types import AccountType
from cfo.ledger.journal import RowIn, post_rows, recompute_opening, record_assertion, revalue
from cfo.ledger.repositories.accounts import (
    AccountRepository,
    AssertionRepository,
    ImportRepository,
    ValuationRepository,
)
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.ledger.setup import AccountInput, add_account
from cfo.metrics.balances import balance
from cfo.metrics.reconcile import gaps
from sqlalchemy.orm import Session

D = date.fromisoformat
TODAY = D("2026-10-20")


def savings(s: Session):  # type: ignore[no-untyped-def]
    return add_account(
        s, AccountInput(AccountType.SAVINGS, "HDFC", "HDFC Savings"), TODAY, "hdfc_bank"
    )


def upload(s: Session, account, rows, closing: int, as_of: str):  # type: ignore[no-untyped-def]
    """What the ingest back half does with one statement."""
    imp = ImportRepository(s).add(
        account.id,
        "f",
        "0" * 64,
        period_start=None,
        period_end=D(as_of),
        rows_inserted=len(rows),
        hashes_ignored=0,
    )
    post_rows(s, account, imp.id, [RowIn(D(d), a, n, n, f"{n}{d}{a}") for d, a, n in rows], {})
    record_assertion(s, account.id, D(as_of), closing, imp.id)
    recompute_opening(s, account.id)
    return imp


def check(s: Session):  # type: ignore[no-untyped-def]
    return gaps(
        AccountRepository(s).list_all(include_retired=True),
        JournalRepository(s).list_all(),
        AssertionRepository(s).list_all(),
    )


def openings(s: Session, account) -> list:  # type: ignore[no-untyped-def,type-arg]
    opening = AccountRepository(s).by_path(OPENING)
    return [
        t
        for t in JournalRepository(s).list_all([account.id])
        if any(p.account_id == opening.id for p in t.postings)
    ]  # type: ignore[union-attr]


def test_first_statement_derives_opening_so_assertion_holds(database: Database) -> None:
    with database.transaction() as s:
        sav = savings(s)
        upload(
            s,
            sav,
            [("2026-09-03", -64000, "SWIGGY"), ("2026-09-10", -200000, "RENT")],
            23373200,
            "2026-09-30",
        )
        assert check(s) == ()
        (opening,) = openings(s, sav)
        assert opening.date == D("2026-09-02") and opening.source == "system"
        assert balance(sav.id, JournalRepository(s).list_all(), D("2026-09-30")) == 23373200


def test_identical_assertion_is_not_stored_twice(database: Database) -> None:
    with database.transaction() as s:
        sav = savings(s)
        assert record_assertion(s, sav.id, D("2026-09-30"), 5, None)
        assert not record_assertion(s, sav.id, D("2026-09-30"), 5, None)
        assert len(AssertionRepository(s).list_all()) == 1


def test_out_of_order_statement_recomputes_opening(database: Database) -> None:
    with database.transaction() as s:
        sav = savings(s)
        upload(s, sav, [("2026-10-05", -10000, "OCT")], 990000, "2026-10-31")
        upload(s, sav, [("2026-09-05", -5000, "SEP")], 1000000, "2026-09-30")
        assert check(s) == ()
        (opening,) = openings(s, sav)
        assert opening.date == D("2026-09-04")


def test_missing_month_shows_a_gap(database: Database) -> None:
    with database.transaction() as s:
        sav = savings(s)
        upload(s, sav, [("2026-09-05", -5000, "SEP")], 1000000, "2026-09-30")
        # October is missing: it spent 23,000 the ledger never saw
        upload(s, sav, [("2026-11-05", -1000, "NOV")], 1000000 - 2300000 - 1000, "2026-11-30")
        (gap,) = check(s)
        assert (gap.as_of, gap.difference) == (D("2026-11-30"), -2300000)


def test_manual_revaluation_posts_to_equity_revaluation(database: Database) -> None:
    with database.transaction() as s:
        fd = add_account(
            s,
            AccountInput(
                AccountType.FIXED_DEPOSIT,
                "SBI",
                "SBI FD",
                opening_value=50000000,
                opening_date=D("2026-04-01"),
            ),
            TODAY,
        )
        assert revalue(s, fd.id, D("2026-09-30"), 51000000) == 1000000
        reval = AccountRepository(s).by_path(REVALUATION)
        txs = JournalRepository(s).list_all([fd.id])
        assert balance(fd.id, txs) == 51000000 and balance(reval.id, txs) == -1000000  # type: ignore[union-attr]
        assert revalue(s, fd.id, D("2026-10-30"), 51000000) == 0


def test_holdings_revaluation_records_valuation_only(database: Database) -> None:
    with database.transaction() as s:
        fund = add_account(
            s, AccountInput(AccountType.MUTUAL_FUND, "Groww", "Groww MF"), TODAY, "groww_mf"
        )
        revalue(s, fund.id, D("2026-09-30"), 1100000)
        assert [v.amount for v in ValuationRepository(s).list_all([fund.id])] == [1100000]
        assert JournalRepository(s).list_all([fund.id]) == []
        with pytest.raises(InvalidInput):  # a bank balance comes from its statements
            revalue(s, savings(s).id, D("2026-09-30"), 5)
