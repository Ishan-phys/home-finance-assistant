"""Statements post through the journal once the ledger is set up (spec §5.2–§5.7)."""

from __future__ import annotations

import json
import re
import threading
from datetime import date
from uuid import uuid4

import pytest
from cfo.categorize.categorizer import ModelClient
from cfo.core.chart import IN_TRANSIT, UNCATEGORIZED_OUT
from cfo.core.errors import NotFoundError, SetupRequired
from cfo.core.types import AccountType, Origin
from cfo.ingest.retry import retry_categorization
from cfo.ingest.upload import upload_statement
from cfo.ledger.journal import recategorize
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
from cfo.parse.base import ParseFailed, ValidationFailed
from cfo.testing import FIXTURE_DIR

TODAY = date(2026, 10, 3)
D = date.fromisoformat


def fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


class FakeModel:
    """Categorizes by keyword into the default categories, answering with whatever key the
    prompt gave each category (keys are aliased when masking is on). Records every request."""

    RULES = [
        ("BILLPAY", "Own account or investment"),
        ("PAYMENT", "Own account or investment"),
        ("SIP", "Own account or investment"),
        ("DEP TFR", "Own account or investment"),
        ("CAFE", "Dining"),
        ("FOOD", "Dining"),
        ("GROCER", "Groceries"),
        ("CASHBACK", "Rewards"),
        ("SALARY", "Salary"),
        ("RENT", "Housing"),
        ("INTEREST", "Interest"),
        ("CAB", "Transport"),
    ]

    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        self.requests.append(system + user)
        keys = {m.group(2): m.group(1) for m in re.finditer(r"^(\S+): (.+?) — ", system, re.M)}
        items = []
        for line in user.splitlines():
            n, rest = line.split(". ", 1)
            desc = rest.split(" ", 1)[1]
            name = next((c for k, c in self.RULES if k in desc.upper()), "Shopping")
            items.append({"id": int(n), "merchant": desc[:12].title(), "category": keys[name]})
        return json.dumps({"items": items})


class Down:
    def complete(self, system: str, user: str) -> str:
        raise ConnectionError("model unreachable")


def accounts(db: Database) -> dict[str, object]:
    with db.transaction() as s:

        def add(t: AccountType, inst: str, name: str, binding: str | None):  # type: ignore[no-untyped-def]
            return add_account(s, AccountInput(t, inst, name), TODAY, binding)

        return {
            "bank": add(AccountType.SAVINGS, "HDFC", "HDFC Savings", "hdfc_bank"),
            "card": add(AccountType.CREDIT_CARD, "HDFC", "HDFC Card", "hdfc_credit_card"),
            "sbi": add(AccountType.SAVINGS, "SBI", "SBI Savings", "sbi_bank"),
            "axis": add(AccountType.CREDIT_CARD, "Axis", "Axis Card", "axis_credit_card"),
            "mf": add(AccountType.MUTUAL_FUND, "Groww", "Groww MF", "groww"),
            "stocks": add(AccountType.STOCK, "Groww", "Groww Stocks", "groww"),
        }


def upload(db: Database, account, name: str, client: ModelClient | None = None, content=None):  # type: ignore[no-untyped-def]
    return upload_statement(
        db, account.id, name, content or fixture(name), client or FakeModel(), TODAY
    )


def txs(db: Database):  # type: ignore[no-untyped-def]
    with db.transaction() as s:
        return JournalRepository(s).list_all()


def counter_path(db: Database, tx) -> str:  # type: ignore[no-untyped-def]
    with db.transaction() as s:
        paths = {a.id: a.path for a in AccountRepository(s).list_all(include_retired=True)}
    (other,) = [p for p in tx.postings if p.origin is not Origin.OBSERVED]
    return paths[other.account_id]


def no_gaps(db: Database) -> bool:
    with db.transaction() as s:
        return (
            gaps(
                AccountRepository(s).list_all(),
                JournalRepository(s).list_all(),
                AssertionRepository(s).list_all(),
            )
            == ()
        )


def test_upload_before_setup_is_refused(database: Database) -> None:
    with pytest.raises(SetupRequired):
        upload_statement(
            database, uuid4(), "hdfc_bank_sep.xls", fixture("hdfc_bank_sep.xls"), FakeModel(), TODAY
        )
    assert txs(database) == []


def test_hdfc_september_produces_balanced_ledger_and_no_gap(database: Database) -> None:
    a = accounts(database)
    fake = FakeModel()
    r = upload(database, a["bank"], "hdfc_bank_sep.xls", fake)
    assert (r.rows_inserted, r.hashes_ignored, r.gaps) == (9, 0, 0)
    assert fake.calls == 1  # one request covers the distinct descriptions
    rows = txs(database)
    assert all(sum(p.amount for p in t.postings) == 0 for t in rows)
    salary = next(t for t in rows if "SALARY" in t.narration)
    assert counter_path(database, salary) == "Income:Salary"
    with database.transaction() as s:
        (assertion,) = AssertionRepository(s).list_all()
        assert (assertion.as_of, assertion.amount) == (D("2026-10-01"), 19245550)
        assert balance(a["bank"].id, JournalRepository(s).list_all(), D("2026-10-01")) == 19245550  # type: ignore[attr-defined]
    assert no_gaps(database)


def test_reupload_is_a_no_op(database: Database) -> None:
    a = accounts(database)
    upload(database, a["bank"], "hdfc_bank_sep.xls")
    before = txs(database)
    with database.transaction() as s:
        assertions_before = AssertionRepository(s).list_all()
    again = upload(database, a["bank"], "hdfc_bank_sep.csv")  # the same rows, other format
    assert again.rows_inserted == 0
    assert len(txs(database)) == len(before)
    with database.transaction() as s:
        assert AssertionRepository(s).list_all() == assertions_before
    assert no_gaps(database)


AUG = (
    b"Statement From : 01/08/2026 To : 25/08/2026\n"
    b"Txn Date,Narration,Withdrawals,Deposits,Closing Balance\n"
    b'10/08/2026,UPI-TEST CAFE-A-UPI,"100.00",,"1,000.00"\n'
    b'20/08/2026,UPI-TEST CAB-B-UPI,"50.00",,"950.00"\n'
)
AUG_LATE = (
    b"Statement From : 15/08/2026 To : 31/08/2026\n"
    b"Txn Date,Narration,Withdrawals,Deposits,Closing Balance\n"
    b'20/08/2026,UPI-TEST CAB-B-UPI,"50.00",,"950.00"\n'
    b'30/08/2026,UPI-TEST GROCER-C-UPI,"25.00",,"925.00"\n'
)


def test_overlapping_statements_add_only_new_rows(database: Database) -> None:
    a = accounts(database)
    upload(database, a["bank"], "aug.csv", content=AUG)
    second = upload(database, a["bank"], "aug2.csv", content=AUG_LATE)
    assert (second.rows_inserted, second.hashes_ignored) == (1, 1)
    assert len(txs(database)) == 4  # three rows and one opening balance
    assert no_gaps(database)


def test_savings_and_card_statements_pair_the_bill_payment(database: Database) -> None:
    a = accounts(database)
    upload(database, a["bank"], "hdfc_bank_sep.xls")
    r = upload(database, a["card"], "hdfc_card_sep.xlsx")
    assert r.pairs_merged == 1
    bill = next(t for t in txs(database) if "BILLPAY" in t.narration)
    assert {p.account_id for p in bill.postings} == {a["bank"].id, a["card"].id}  # type: ignore[attr-defined]
    with database.transaction() as s:
        card_assertion = next(
            x for x in AssertionRepository(s).list_all() if x.account_id == a["card"].id
        )  # type: ignore[attr-defined]
        assert card_assertion.amount == -1006400  # what is owed is a negative liability
        assert ImportRepository(s).list_all(a["card"].id)[0].amount_due == 1006400  # type: ignore[attr-defined]
    assert no_gaps(database)


def test_upload_never_posts_to_retired_category(database: Database) -> None:
    a = accounts(database)
    upload(database, a["bank"], "hdfc_bank_sep.xls")
    cafe = next(
        t for t in txs(database) if "TEST CAFE" in t.narration and t.date == D("2026-09-09")
    )
    with database.transaction() as s:
        gym = AccountRepository(s).by_path("Expenses:Health")
        recategorize(s, cafe.id, gym.id)  # type: ignore[union-attr]
        AccountRepository(s).retire(gym.id, TODAY)  # type: ignore[union-attr]
    later = (
        b"Statement From : 01/10/2026 To : 31/10/2026\n"
        b"Txn Date,Narration,Withdrawals,Deposits,Closing Balance\n"
        b'09/10/2026,UPI-TEST CAFE-TESTCAFE-REF000009-UPI,"250.00",,"1,92,205.50"\n'
    )
    upload(database, a["bank"], "oct.csv", Down(), content=later)
    october = next(t for t in txs(database) if t.date == D("2026-10-09"))
    assert counter_path(database, october) == UNCATEGORIZED_OUT


def test_groww_orders_never_reach_the_model_and_wait_in_transit(database: Database) -> None:
    a = accounts(database)
    fake = FakeModel()
    r = upload(database, a["mf"], "groww_mf_orders.xlsx", fake)
    assert r.rows_inserted == 4 and fake.calls == 0
    assert {counter_path(database, t) for t in txs(database) if t.source == "import"} == {
        IN_TRANSIT
    }


def test_holdings_files_record_valuations_not_balances(database: Database) -> None:
    a = accounts(database)
    upload(database, a["mf"], "groww_mf_holdings.xlsx")
    upload(database, a["stocks"], "groww_stocks_holdings.xlsx")
    with database.transaction() as s:
        vals = {(v.account_id, v.amount) for v in ValuationRepository(s).list_all()}
        assert vals == {(a["mf"].id, 11200050), (a["stocks"].id, 8536529)}  # type: ignore[attr-defined]
        assert AssertionRepository(s).list_all() == []
    mismatched = upload(database, a["mf"], "groww_stocks_holdings.xlsx")
    assert any("stocks file" in w for w in mismatched.warnings)


def test_rejected_files_write_nothing(database: Database) -> None:
    a = accounts(database)
    with pytest.raises((ParseFailed, ValidationFailed)):
        upload(database, a["bank"], "x.csv", content=b"not a statement")
    with pytest.raises(NotFoundError):
        upload_statement(database, uuid4(), "x.csv", AUG, FakeModel(), TODAY)
    assert txs(database) == []


def test_model_down_keeps_rows_uncategorized_then_retry_fills_them(database: Database) -> None:
    a = accounts(database)
    r = upload(database, a["bank"], "hdfc_bank_sep.xls", Down())
    assert r.uncategorized == 9
    assert any("could not be reached" in w for w in r.warnings)
    fixed = retry_categorization(database, FakeModel(), database.default_scope)
    assert fixed.rows_updated == 9
    rows = [t for t in txs(database) if t.source == "import"]
    assert {counter_path(database, t) for t in rows} >= {
        "Income:Salary",
        "Expenses:Housing",
    }


def test_concurrent_uploads_of_the_same_file_serialize(database: Database) -> None:
    a = accounts(database)
    results = []

    def go() -> None:
        results.append(upload(database, a["bank"], "hdfc_bank_sep.xls"))

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r.rows_inserted for r in results) == [0, 9]


def test_removing_a_statement_keeps_rows_another_statement_also_holds(database: Database) -> None:
    a = accounts(database)  # final review I2
    first = upload(database, a["bank"], "aug.csv", content=AUG)
    second = upload(database, a["bank"], "aug2.csv", content=AUG_LATE)
    assert second.hashes_ignored == 1
    from cfo.ledger.journal import remove_import

    with database.transaction() as s:
        remove_import(s, first.import_id)
    kept = sorted(
        p.amount
        for t in txs(database)
        if t.source == "import"
        for p in t.postings
        if p.origin is Origin.OBSERVED
    )
    assert kept == [-5000, -2500]  # the shared 50.00 row stays, with the row only B has
    assert no_gaps(database)


def test_the_same_file_twice_survives_removing_the_first(database: Database) -> None:
    a = accounts(database)  # final review I2, simplest trigger
    first = upload(database, a["bank"], "aug.csv", content=AUG)
    again = upload(database, a["bank"], "aug-again.csv", content=AUG)
    assert again.rows_inserted == 0 and any("already uploaded" in w for w in again.warnings)
    from cfo.ledger.journal import remove_import

    with database.transaction() as s:
        remove_import(s, first.import_id)
    assert len([t for t in txs(database) if t.source == "import"]) == 2
    assert no_gaps(database)


def test_owner_rule_categorizes_before_the_model_and_beats_it(database: Database) -> None:
    from cfo.ledger.repositories.rules import RuleRepository
    from cfo.rules import MatchMode

    accts = accounts(database)
    with database.transaction() as s:
        RuleRepository(s).add(
            "Cafe is fitness", "cafe", MatchMode.CONTAINS, "debit", "Expenses:Health"
        )
    model = FakeModel()
    upload(database, accts["bank"], "hdfc_bank_sep.csv", model)
    cafes = [
        t
        for t in txs(database)
        if "CAFE" in t.narration.upper()
        and next(p for p in t.postings if p.origin is Origin.OBSERVED).amount < 0
    ]
    assert cafes and all(counter_path(database, t) == "Expenses:Health" for t in cafes)
    asked = "\n".join(model.requests).upper()
    assert all(
        t.narration.upper() not in asked for t in cafes
    )  # a rule row never reached the model
    with database.transaction() as s:
        from cfo.ledger.verify import verify_books

        assert verify_books(s) == []


def test_a_hand_decision_reaches_the_model_as_an_example_on_retry(database: Database) -> None:
    from cfo.categorize.categorizer import CategorizationResult

    class Recording:
        def __init__(self) -> None:
            self.examples: list = []
            self.asked: list[str] = []

        def categorize(self, items, labels, examples=()):  # type: ignore[no-untyped-def]
            self.examples, self.asked = list(examples), [i.description for i in items]
            return CategorizationResult()

    accts = accounts(database)
    upload(database, accts["bank"], "hdfc_bank_sep.csv", Down())  # nothing categorized
    cafe = next(
        t for t in txs(database) if "TEST CAFE" in t.narration and "REFUND" not in t.narration
    )
    with database.transaction() as s:
        health = AccountRepository(s).by_path("Expenses:Health")
        recategorize(s, cafe.id, health.id)
    model = Recording()
    retry_categorization(database, model)
    assert any("CAFE REFUND" in d for d in model.asked)
    (example,) = model.examples
    assert example.description == cafe.narration
    assert example.label.startswith("category_")  # the model sees a key, never the real path
