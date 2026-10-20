"""The sample ledger end to end: the fixtures' figures, derived by hand (fixtures/
expected_results.json), against the reports."""

from __future__ import annotations

import json
from datetime import date

from cfo.api.sample import load_sample_into
from cfo.ledger import reports
from cfo.ledger.repositories.db import Database
from cfo.testing import FIXTURE_DIR, SeedClient

AS_OF = date(2026, 10, 3)
EXPECTED = json.loads((FIXTURE_DIR / "expected_results.json").read_text())


def paise(x: dict) -> int:  # type: ignore[type-arg]
    return int(x["paise"])


def test_the_sample_ledger_matches_the_hand_derived_figures(database: Database) -> None:
    result = load_sample_into(database, database.default_scope, AS_OF, SeedClient())
    assert result.accounts == 6
    assert result.uploads[2].pairs_merged == 1  # the HDFC card payment found its bank debit
    with database.transaction() as s:
        data = reports.load(s, AS_OF)
    sheet = reports.balance_sheet_report(data)
    month = reports.income_statement_report(data, EXPECTED["month"])
    sts = reports.safe_to_spend_report(data)
    inbox = reports.inbox_report(data)
    got = {
        "net_worth": paise(sheet["net_worth"]),
        "groups": {g["group"]: paise(g["total"]) for g in sheet["groups"]},
        "earned": paise(month["earned"]),
        "spent": paise(month["spent"]),
        "rewards": paise(month["rewards"]),
        "saved": paise(month["saved"]),
        "safe_to_spend": paise(sts["amount"]),
        "inbox": sorted(i["kind"] for i in inbox),
    }
    assert got == EXPECTED["figures"]
    assert month["check"]["ok"] is True
    for t in data.transactions:
        assert sum(p.amount for p in t.postings) == 0


def test_reloading_the_same_statements_changes_nothing(database: Database) -> None:
    from cfo.ingest.upload import upload_statement

    load_sample_into(database, database.default_scope, AS_OF, SeedClient())
    with database.transaction() as s:
        before = reports.balance_sheet_report(reports.load(s, AS_OF))
        accounts = reports.load(s, AS_OF).accounts
    bank = next(a for a in accounts if a.display_name == "Sample HDFC Savings")
    r = upload_statement(
        database,
        bank.id,
        "again.xls",
        (FIXTURE_DIR / "hdfc_bank_sep.xls").read_bytes(),
        SeedClient(),
        AS_OF,
    )
    assert r.rows_inserted == 0
    with database.transaction() as s:
        assert reports.balance_sheet_report(reports.load(s, AS_OF)) == before
