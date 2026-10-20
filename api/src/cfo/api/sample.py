"""'Load sample statements': a person with one account per statement format, set up and with the
synthetic fixtures imported, so the demo needs no personal data and no live model."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from cfo.api.catalog import resolve_binding
from cfo.categorize.seed import SeedClient
from cfo.core.errors import ConflictError
from cfo.core.ids import Id
from cfo.core.types import AccountRole, AccountType, Scope
from cfo.ingest.upload import UploadResult, upload_statement
from cfo.ledger.repositories.accounts import AccountRepository
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.people import PeopleRepository
from cfo.ledger.setup import AccountInput, add_account, complete_setup
from cfo.redact import Redactor, RedactorConfig


def find_fixture_dir() -> Path:
    """The synthetic statements: `CFO_FIXTURE_DIR`, else the nearest `fixtures/` above here."""
    explicit = os.environ.get("CFO_FIXTURE_DIR")
    if explicit:
        return Path(explicit)
    for parent in Path(__file__).resolve().parents:
        if (parent / "fixtures" / "merchant_mappings.json").exists():
            return parent / "fixtures"
    raise RuntimeError("sample fixtures not found; set CFO_FIXTURE_DIR")


FIXTURE_DIR = find_fixture_dir()


def default_seed_client() -> SeedClient:
    """Merchant mappings from the checked-in file, so the demo needs no live model."""
    redactor = Redactor(RedactorConfig(salt=b"seed-keys-are-matched-by-shape-0"))
    return SeedClient.from_file(FIXTURE_DIR / "merchant_mappings.json", redactor.redact_text)


@dataclass(frozen=True, slots=True)
class SampleResult:
    accounts: int
    uploads: list[UploadResult]
    person_id: Id | None = None


_ACCOUNTS: list[tuple[AccountType, str, str, list[str]]] = [
    (AccountType.SAVINGS, "HDFC Bank", "Sample HDFC Savings", ["hdfc_bank_sep.xls"]),
    (AccountType.SAVINGS, "SBI", "Sample SBI Savings", ["sbi_bank_sep.xlsx"]),
    (AccountType.CREDIT_CARD, "HDFC Bank", "Sample HDFC Card", ["hdfc_card_sep.xlsx"]),
    (AccountType.CREDIT_CARD, "Axis Bank", "Sample Axis Card", ["axis_card_sep.pdf"]),
    (
        AccountType.MUTUAL_FUND,
        "Groww",
        "Sample Groww Mutual Funds",
        ["groww_mf_holdings.xlsx", "groww_mf_orders.xlsx"],
    ),
    (AccountType.STOCK, "Groww", "Sample Groww Stocks", ["groww_stocks_holdings.xlsx"]),
]


def load_sample(db: Database, today: date, client: SeedClient | None = None) -> SampleResult:
    """Create a "Sample Person" and load the sample into their ledger. Allowed only while there
    are no people, so the demo never mixes with real data."""
    with db.transaction() as s:
        people = PeopleRepository(s)
        if people.any():
            raise ConflictError("sample statements can only be loaded before anyone is added")
        person, ledger = people.create("Sample Person")
    return load_sample_into(db, Scope.of(ledger.id), today, client, person_id=person.id)


def load_sample_into(
    db: Database,
    scope: Scope,
    today: date,
    client: SeedClient | None = None,
    *,
    person_id: Id | None = None,
) -> SampleResult:
    """Set up the sample accounts in an empty ledger and import the synthetic statements."""
    with db.transaction(scope) as s:
        if AccountRepository(s).list_all(AccountRole.REAL):
            raise ConflictError("sample statements can only be loaded into an empty ledger")
    seed = client or default_seed_client()
    ids: list[Id] = []
    with db.transaction(scope) as s:
        for type, institution, name, _ in _ACCOUNTS:
            account = add_account(
                s, AccountInput(type, institution, name), today, resolve_binding(institution, type)
            )
            ids.append(account.id)
        complete_setup(s, datetime.now(UTC))
    uploads = [
        upload_statement(
            db, account_id, file, (FIXTURE_DIR / file).read_bytes(), seed, today, scope=scope
        )
        for account_id, (_, _, _, files) in zip(ids, _ACCOUNTS, strict=True)
        for file in files
    ]
    return SampleResult(len(ids), uploads, person_id)
