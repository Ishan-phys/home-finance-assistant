"""Reports: one load, pure metrics, plain JSON (spec §5.11)."""

from __future__ import annotations

import json
from datetime import date

from cfo.core.types import AccountType, MappingSource, MerchantMapping
from cfo.ledger import reports
from cfo.ledger.journal import (
    RowIn,
    pair_in_transit,
    post_rows,
    recompute_opening,
    record_assertion,
)
from cfo.ledger.repositories.accounts import ImportRepository, SettingsRepository
from cfo.ledger.repositories.db import Database
from cfo.ledger.setup import AccountInput, add_account
from sqlalchemy.orm import Session

D = date.fromisoformat
TODAY = D("2026-10-03")
M = MerchantMapping


def statement(s: Session, account, rows, closing: int, as_of: str, maps=None) -> None:  # type: ignore[no-untyped-def]
    imp = ImportRepository(s).add(
        account.id,
        f"{account.display_name}.csv",
        "0" * 64,
        period_start=None,
        period_end=D(as_of),
        rows_inserted=0,
        hashes_ignored=0,
    )
    post_rows(
        s,
        account,
        imp.id,
        [RowIn(D(d), a, n, n.title(), f"{n}{d}{a}", own) for d, a, n, own in rows],
        maps or {},
    )
    pair_in_transit(s)
    record_assertion(s, account.id, D(as_of), closing, imp.id)
    recompute_opening(s, account.id)


def books(database: Database):  # type: ignore[no-untyped-def]
    maps = {
        "SALARY": M("SALARY", "Testcorp", "Income:Salary", MappingSource.MODEL),
        "SWIGGY": M("SWIGGY", "Swiggy", "Expenses:Food:Dining", MappingSource.MODEL),
        "GROCER": M("GROCER", "Grocer", "Expenses:Food:Groceries", MappingSource.MODEL),
        "FRIEND": M("FRIEND", "Personal transfer", "Expenses:People:Sent", MappingSource.MODEL),
    }
    with database.transaction() as s:
        sav = add_account(
            s, AccountInput(AccountType.SAVINGS, "HDFC", "HDFC Savings"), TODAY, "hdfc_bank"
        )
        card = add_account(
            s, AccountInput(AccountType.CREDIT_CARD, "HDFC", "HDFC Card"), TODAY, "hdfc_credit_card"
        )
        statement(
            s,
            sav,
            [
                ("2026-09-01", 15000000, "SALARY", False),
                ("2026-09-04", -1626800, "CC BILLPAY", True),
                ("2026-09-05", -64000, "SWIGGY", False),
                ("2026-09-06", -200000, "FRIEND", False),
                ("2026-09-07", -120000, "MYSTERY", False),
            ],
            23373200,
            "2026-09-30",
            maps,
        )
        statement(
            s,
            card,
            [
                ("2026-09-03", -30000, "GROCER", False),
                ("2026-09-04", 1626800, "PAYMENT RECEIVED", True),
            ],
            -30000,
            "2026-09-20",
            maps,
        )
        ImportRepository(s).add(
            card.id,
            "due",
            "0" * 64,
            period_start=None,
            period_end=D("2026-09-20"),
            rows_inserted=0,
            hashes_ignored=0,
            amount_due=30000,
            due_date=D("2026-10-10"),
        )
        SettingsRepository(s).update(min_cash_buffer=5000000)
    return sav, card


def data(database: Database):  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        return reports.load(s, TODAY)


def test_overview_numbers_agree_with_balance_sheet_and_statement(database: Database) -> None:
    books(database)
    d = data(database)
    overview = reports.overview_report(d)
    sheet = reports.balance_sheet_report(d)
    month = reports.income_statement_report(d, "2026-09")
    assert (
        overview["net_worth"]["total"]
        == sheet["net_worth"]
        == {"paise": 23373200 - 30000, "formatted": "₹2,33,432.00"}
    )
    assert overview["this_month"]["month"] == "2026-10"
    assert month["earned"]["paise"] == 15000000
    assert month["spent"]["paise"] == 64000 + 30000 + 120000
    assert month["people_out"]["paise"] == 200000
    assert overview["safe_to_spend"]["amount"]["paise"] == 23373200 - 5000000 - 30000
    json.dumps(overview), json.dumps(sheet), json.dumps(month)  # plain JSON


def test_balance_sheet_groups_and_names(database: Database) -> None:
    books(database)
    sheet = reports.balance_sheet_report(data(database))
    groups = {g["group"]: g for g in sheet["groups"]}
    assert groups["owed"]["total"]["paise"] == -30000 and groups["owed"]["label"] == "What I owe"
    assert [a["name"] for a in groups["liquid"]["accounts"]] == ["HDFC Savings"]


def test_transactions_are_shown_from_to(database: Database) -> None:
    books(database)
    rows = {r["narration"]: r for r in reports.transactions_report(data(database))}
    assert (rows["SALARY"]["from"]["name"], rows["SALARY"]["to"]["name"]) == (
        "Salary",
        "HDFC Savings",
    )
    assert (rows["CC BILLPAY"]["from"]["name"], rows["CC BILLPAY"]["to"]["name"]) == (
        "HDFC Savings",
        "HDFC Card",
    )
    assert rows["CC BILLPAY"]["category"] is None and rows["SWIGGY"]["category"]["name"] == "Dining"
    assert rows["SWIGGY"]["amount"]["paise"] == 64000 and len(rows["SWIGGY"]["postings"]) == 2
    only_card = reports.transactions_report(data(database), q="grocer")
    assert [r["narration"] for r in only_card] == ["GROCER"]


def test_inbox_texts_are_plain_language(database: Database) -> None:
    books(database)
    items = reports.inbox_report(data(database))
    by_kind = {i["kind"]: i for i in items}
    assert by_kind["uncategorized"]["action"] == "categorize"
    assert "needs a category" in by_kind["uncategorized"]["text"]
    assert by_kind["card_due"]["text"] == "HDFC Card bill of ₹300.00 is due on 10 Oct 2026"
    assert "unpaired" not in by_kind  # the bill payment paired


def test_check_line_is_ok(database: Database) -> None:
    books(database)
    month = reports.income_statement_report(data(database), "2026-09")
    assert month["check"]["ok"] is True
    tree = month["categories"]["out"]
    food = next(n for n in tree if n["path"] == "Expenses:Food")
    assert food["amount"]["paise"] == 94000 and {c["name"] for c in food["children"]} == {
        "Dining",
        "Groceries",
    }


def test_account_report_register_and_statements(database: Database) -> None:
    sav, _ = books(database)
    page = reports.account_report(data(database), sav.id)
    assert page["account"]["balance"]["paise"] == 23373200
    assert page["register"][0]["running"]["paise"] == 23373200  # newest first
    assert page["statements"][0]["assertion_ok"] is True


def test_categories_and_tree(database: Database) -> None:
    books(database)
    d = data(database)
    cats = reports.categories_report(d)
    dining = next(c for c in cats["out"] if c["name"] == "Dining")
    assert dining["description"] and dining["used"] == 1 and dining["default"] is True
    assert cats["own_move"]["name"] == "Own account or investment" and cats["own_move"]["id"]
    tree = reports.accounts_tree_report(d)
    assert [k["label"] for k in tree["kinds"]] == [
        "Assets",
        "Liabilities",
        "Income",
        "Expenses",
        "Equity",
    ]


def test_leaks_lists_this_months_top_payees_even_without_a_baseline(database: Database) -> None:
    books(database)
    r = reports.leaks_report(data(database), "2026-09")
    assert r["reason"] == "NO_BASELINE"
    assert [x["payee"] for x in r["current"]][:1] == ["Mystery"]
