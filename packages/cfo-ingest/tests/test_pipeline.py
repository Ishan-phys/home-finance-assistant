"""The ingestion pipeline's guarantees: nothing personal is stored or sent, and it fails closed."""

from __future__ import annotations

import io
import json
from datetime import date

import openpyxl
import pytest
from cfo.core.errors import RedactionFailed
from cfo.core.types import AccountType, Origin
from cfo.ingest.upload import upload_statement
from cfo.ledger.repositories.accounts import (
    AccountRepository,
    ImportRepository,
    RedactionTermRepository,
)
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.ledger.setup import AccountInput, add_account
from cfo.parse.readers import read_document
from cfo.parse.registry import ADAPTERS
from cfo.redact import Redactor, RedactorConfig
from cfo.testing import FIXTURE_DIR

TODAY = date(2026, 10, 3)
PRIVATE = [
    "MIRA",
    "KULKARNI",
    "TARA",
    "NAIR",
    "9876543210",
    "ABCDE1234F",
    "mira.k@example.com",
    "44 LAKE VIEW ROAD",
    "PUNE 411001",
    "00112233445566",
    "22334455",
    "tara.n@okhdfc",
]


def real_shaped_workbook() -> bytes:
    """An HDFC-shaped workbook with invented personal details in the preamble and narrations."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in [
        ["HDFC BANK Ltd."],
        ["MASTER MIRA KULKARNI", None, None, None, "Account Branch :PUNE"],
        ["44 LAKE VIEW ROAD", None, None, None, "Phone no. :9876543210"],
        ["PUNE 411001", None, None, None, "Email :MIRA.K@EXAMPLE.COM"],
        ["JOINT HOLDERS : TARA NAIR", None, None, None, "Account No :00112233445566   INFINITI"],
        ["PAN: ABCDE1234F", None, None, None, "Cust ID :22334455"],
        ["Statement From  :  01/09/2026         To  :  30/09/2026"],
        [
            "Date",
            "Narration",
            "Chq./Ref.No.",
            "Value Dt",
            "Withdrawal Amt.",
            "Deposit Amt.",
            "Closing Balance",
        ],
        ["********"] * 7,
        [
            "02/09/26",
            "UPI-TARA NAIR-tara.n@okhdfc-IDFB0040101-412345678901-Dinner",
            "0000412345678901",
            "02/09/26",
            600.0,
            None,
            99400.0,
        ],
        [
            "04/09/26",
            "UPI/9876543210/Mira Kulkarni",
            "0000629107156674",
            "04/09/26",
            500.0,
            None,
            98900.0,
        ],
        [
            "05/09/26",
            "UPI-SWIGGY-swiggy@icici-ICIC0000001-1-Order",
            "0000629107156675",
            "05/09/26",
            250.0,
            None,
            98650.0,
        ],
    ]:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


class Spy:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.requests.append(system + user)
        dining = next(
            line.split(": ", 1)[0] for line in system.splitlines() if ": Dining — " in line
        )
        items = [
            {"id": int(line.split(". ", 1)[0]), "merchant": "Swiggy", "category": dining}
            for line in user.splitlines()
            if "SWIGGY" in line
        ]
        return json.dumps({"items": items})


def account(database: Database, binding: str = "hdfc_bank") -> object:
    with database.transaction() as s:
        return add_account(
            s, AccountInput(AccountType.SAVINGS, "HDFC", "Savings One"), TODAY, binding
        ).id


def rows_of(database: Database) -> list[tuple[str, str, int, date]]:
    """(narration, payee, observed amount, date) of every imported row."""
    with database.transaction() as s:
        out = []
        for t in JournalRepository(s).list_all():
            for p in t.postings:
                if p.origin is Origin.OBSERVED:
                    out.append((t.narration, t.payee, p.amount, t.date))
        return out


def test_nothing_personal_is_stored_or_sent(database: Database) -> None:
    acc = account(database)
    with database.transaction() as s:
        RedactionTermRepository(s).replace(["Mira Kulkarni", "Mira", "Kulkarni"])
    spy = Spy()
    result = upload_statement(database, acc, "s.xlsx", real_shaped_workbook(), spy, TODAY)
    assert result.rows_inserted == 3
    rows = rows_of(database)
    with database.transaction() as s:
        record = ImportRepository(s).history()[0]
        stored_account = AccountRepository(s).get(acc)  # type: ignore[arg-type]
    haystack = "\n".join(
        [f"{narration}\n{payee}" for narration, payee, _, _ in rows]
        + spy.requests
        + [json.dumps(record, default=str), repr(stored_account)]
    )
    for private in PRIVATE:
        assert private.upper() not in haystack.upper(), private
    assert "SWIGGY" in haystack.upper()  # merchants stay readable
    # amounts and dates are exactly what the file said
    assert sorted(r[2] for r in rows) == [-60000, -50000, -25000]
    assert {r[3] for r in rows} == {date(2026, 9, 2), date(2026, 9, 4), date(2026, 9, 5)}
    # the import records what was redacted, by class, never the values
    assert result.redaction and set(result.redaction) >= {
        "PERSON",
        "ADDRESS",
        "EMAIL",
        "PHONE",
        "PAN",
    }
    assert record["redaction_summary"] == result.redaction
    assert all(isinstance(v, int) for v in result.redaction.values())


def test_every_fixture_parses_the_same_after_redaction() -> None:
    redactor = Redactor(RedactorConfig(salt=b"s" * 32, terms=("Fixture Person",)))
    files = {
        "hdfc_bank": ["hdfc_bank_sep.xls", "hdfc_bank_sep.csv"],
        "sbi_bank": ["sbi_bank_sep.xlsx"],
        "hdfc_credit_card": ["hdfc_card_sep.xlsx"],
        "axis_credit_card": ["axis_card_sep.pdf"],
        "groww": ["groww_mf_holdings.xlsx", "groww_stocks_holdings.xlsx", "groww_mf_orders.xlsx"],
    }
    for binding, names in files.items():
        for name in names:
            doc = read_document(name, (FIXTURE_DIR / name).read_bytes())
            raw = ADAPTERS[binding].parse(doc)
            red = ADAPTERS[binding].parse(redactor.redact(doc).document)
            key = lambda p: (  # noqa: E731
                [(r.date, r.amount) for r in p.rows],
                p.closing_balance,
                p.period_end,
                p.amount_due,
                p.due_date,
                p.balance_as_of,
            )
            assert key(raw) == key(red), name


def test_the_pipeline_fails_closed(database: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    import cfo.redact.redactor as module

    acc = account(database)

    def boom(self, text):  # type: ignore[no-untyped-def]
        raise ValueError("kaboom")

    monkeypatch.setattr(module._Run, "scrub", boom)
    spy = Spy()
    with pytest.raises(RedactionFailed, match="nothing was imported"):
        upload_statement(database, acc, "s.xlsx", real_shaped_workbook(), spy, TODAY)
    assert spy.requests == []  # nothing unredacted went anywhere
    with database.transaction() as s:
        assert JournalRepository(s).list_all() == [] and ImportRepository(s).list_all() == []


def test_account_fingerprint_binds_then_warns_on_a_misplaced_statement(database: Database) -> None:
    acc = account(database)
    first = upload_statement(database, acc, "s.xlsx", real_shaped_workbook(), None, TODAY)
    assert not any("differs" in w for w in first.warnings)
    with database.transaction() as s:
        fingerprint = AccountRepository(s).get(acc).statement_fingerprint  # type: ignore[union-attr,arg-type]
    assert fingerprint and "0011223344" not in fingerprint
    same = upload_statement(database, acc, "s2.xlsx", real_shaped_workbook(), None, TODAY)
    assert not any("differs" in w for w in same.warnings)
    other = real_shaped_workbook().replace(b"x", b"x")  # same bytes: build a different account no
    wb = openpyxl.load_workbook(io.BytesIO(other))
    wb.active["E5"] = "Account No :99887766554433   INFINITI"  # type: ignore[index]
    out = io.BytesIO()
    wb.save(out)
    warned = upload_statement(database, acc, "s3.xlsx", out.getvalue(), None, TODAY)
    assert any("differs" in w and "Savings One" in w for w in warned.warnings)


def test_a_different_salt_gives_different_tokens_for_the_same_payee() -> None:
    doc = read_document("s.xlsx", real_shaped_workbook())
    a = Redactor(RedactorConfig(salt=b"a" * 32)).redact(doc).document
    b = Redactor(RedactorConfig(salt=b"b" * 32)).redact(doc).document
    assert a != b


# the System-1 categorizer through the pipeline ----------------------------------------


def _decision(category: str, confidence: float, who: str = "merchant"):  # type: ignore[no-untyped-def]
    from openai.types import Decision

    cats = [category, "unclear"]
    parties = ["merchant", "person", "own_account", "unclear"]

    def answer(name: str, value: str, conf: float, options: list[str]) -> dict:  # type: ignore[type-arg]
        return {
            "type": "choice",
            "name": name,
            "choice": value,
            "confidence": conf,
            "probabilities": [{"value": o, "probability": 1.0 / len(options)} for o in options],
        }

    return Decision.model_validate(
        {
            "answers": [
                answer("category", category, confidence, cats),
                answer("counterparty", who, 0.9, parties),
            ],
            "model": "gpt-6-luna",
            "usage": {
                "input_tokens": 100,
                "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
                "output_tokens": 0,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 100,
            },
        }
    )


class _FakeDecisions:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def create(self, **kw):  # type: ignore[no-untyped-def]
        self.inputs.append(kw["input"] + str(kw["questions"]))
        choices = kw["questions"][0]["choices"]

        def key(name: str) -> str:
            return next(c["value"] for c in choices if c["description"].startswith(f"{name}:"))

        if "Order" in kw["input"]:
            return _decision(key("Dining"), 0.95)
        return _decision(key("Shopping"), 0.40)  # too unsure to use


class _FakeDecisionsClient:
    def __init__(self) -> None:
        self.decisions = _FakeDecisions()


def test_the_decisions_categorizer_runs_through_the_pipeline_and_keeps_its_confidence(
    database: Database,
) -> None:
    from cfo.categorize.decisions import DecisionsCategorizer

    acc = account(database)
    client = _FakeDecisionsClient()
    upload_statement(
        database,
        acc,
        "s.xlsx",
        real_shaped_workbook(),
        DecisionsCategorizer(client),
        TODAY,  # type: ignore[arg-type]
    )
    sent = "\n".join(client.decisions.inputs)
    for private in PRIVATE:
        assert private.upper() not in sent.upper(), private  # only redacted text reaches it
    assert "Direction: debit (money out)" in sent
    from cfo.ledger.repositories.transactions import MappingRepository

    with database.transaction() as s:
        accounts = {x.id: x.path for x in AccountRepository(s).list_all()}
        txs = JournalRepository(s).list_all()
        stored = MappingRepository(s).get_many(t.narration for t in txs)

    def counter(t):  # type: ignore[no-untyped-def]
        return next(accounts[p.account_id] for p in t.postings if p.origin is not Origin.OBSERVED)

    swiggy = next(t for t in txs if "SWIGGY" in t.narration)
    assert counter(swiggy) == "Expenses:Food:Dining" and swiggy.payee == "Swiggy"
    assert stored[swiggy.narration].confidence == pytest.approx(0.95)
    unsure = [t for t in txs if "SWIGGY" not in t.narration and t.source == "import"]
    assert unsure and {counter(t) for t in unsure} == {"Expenses:Uncategorized"}  # 0.40 < 0.6
