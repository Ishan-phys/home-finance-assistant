"""Schema and scoped repositories for the double-entry ledger (spec §4)."""

from __future__ import annotations

import threading
import time
from datetime import date

import pytest
from alembic import command
from cfo.core.chart import IN_TRANSIT, OPENING
from cfo.core.ids import new_id
from cfo.core.types import (
    Account,
    AccountKind,
    AccountRole,
    AccountType,
    MappingSource,
    MerchantMapping,
    Origin,
    Posting,
    Scope,
    Transaction,
)
from cfo.ledger.repositories.accounts import (
    AccountRepository,
    AssertionRepository,
    ImportRepository,
    SettingsRepository,
    ValuationRepository,
)
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.people import PeopleRepository
from cfo.ledger.repositories.transactions import JournalRepository, MappingRepository
from cfo.testing.pg import alembic_config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

D = date.fromisoformat
OBS, INF, SYS = Origin.OBSERVED, Origin.INFERRED, Origin.SYSTEM


def account(
    path: str, kind: AccountKind, role: AccountRole = AccountRole.REAL, **kw: object
) -> Account:
    return Account(new_id(), path, kind, role, path.rsplit(":", 1)[-1], **kw)  # type: ignore[arg-type]


def savings() -> Account:
    t = AccountType.SAVINGS
    return account("Assets:Bank:HDFC:Savings", t.kind, type=t, group=t.group, binding="hdfc_bank")


def card() -> Account:
    t = AccountType.CREDIT_CARD
    return account(
        "Liabilities:Cards:HDFC:Card", t.kind, type=t, group=t.group, binding="hdfc_card"
    )


def tx(day: str, *legs: tuple[Account, int, Origin], h: str | None = None, imp=None) -> Transaction:  # type: ignore[no-untyped-def]
    postings = tuple(
        Posting(a.id, amt, o, dedup_hash=h if o is OBS and i == 0 else None, import_id=imp)
        for i, (a, amt, o) in enumerate(legs)
    )
    return Transaction(new_id(), D(day), "NARR", "Payee", postings, import_id=imp)


@pytest.fixture
def books(database: Database):  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        repo = AccountRepository(s)
        sav, crd = repo.add(savings()), repo.add(card())
        # every ledger starts with its system accounts and default categories
        transit, opening = repo.by_path(IN_TRANSIT), repo.by_path(OPENING)
        food = repo.by_path("Expenses:Food:Dining")
    return sav, crd, transit, opening, food


def test_round_trip_and_postings_cascade_with_their_transaction(database, books) -> None:  # type: ignore[no-untyped-def]
    sav, _, _, _, food = books
    t = tx("2026-09-03", (sav, -64000, OBS), (food, 64000, INF), h="h1")
    with database.transaction() as s:
        JournalRepository(s).add(t)
    with database.transaction() as s:
        got = JournalRepository(s).get(t.id)
        assert got is not None and sorted(p.amount for p in got.postings) == [-64000, 64000]
        assert JournalRepository(s).existing_hashes(sav.id, ["h1", "h2"]) == {"h1"}
        assert [x.id for x in JournalRepository(s).list_all([food.id])] == [t.id]
        JournalRepository(s).delete(t.id)
    with database.transaction() as s:
        assert s.execute(text("SELECT count(*) FROM postings")).scalar() == 0


def test_hashes_are_unique_per_account(database, books) -> None:  # type: ignore[no-untyped-def]
    sav, _, _, _, food = books
    with database.transaction() as s:
        JournalRepository(s).add(tx("2026-09-03", (sav, -1, OBS), (food, 1, INF), h="same"))
    with pytest.raises(IntegrityError), database.transaction() as s:
        JournalRepository(s).add(tx("2026-09-04", (sav, -2, OBS), (food, 2, INF), h="same"))


def test_cannot_post_to_another_ledgers_account(database, books) -> None:  # type: ignore[no-untyped-def]
    sav, *_ = books
    with database.transaction() as s:
        _, other = PeopleRepository(s).create("Ben Mills")
    with database.transaction(Scope.of(other.id)) as s:
        theirs = AccountRepository(s).add(
            account("Expenses:Misc", AccountKind.EXPENSE, AccountRole.CATEGORY)
        )
    with pytest.raises(IntegrityError), database.transaction() as s:
        JournalRepository(s).add(tx("2026-09-03", (sav, -5, OBS), (theirs, 5, INF)))


def test_merge_combines_two_in_transit_halves(database, books) -> None:  # type: ignore[no-untyped-def]
    sav, crd, transit, _, _ = books
    t1 = tx("2026-09-04", (sav, -1626800, OBS), (transit, 1626800, INF), h="a")
    t2 = tx("2026-09-05", (crd, 1626800, OBS), (transit, -1626800, INF), h="b")
    with database.transaction() as s:
        repo = JournalRepository(s)
        repo.add(t1), repo.add(t2)
        halves = repo.in_transit_halves()
        assert {(h.tx_id, h.amount) for h in halves} == {(t1.id, 1626800), (t2.id, -1626800)}
        repo.merge(t1.id, t2.id)
    with database.transaction() as s:
        repo = JournalRepository(s)
        merged = repo.get(t1.id)
        assert merged is not None and repo.get(t2.id) is None
        assert sorted(p.amount for p in merged.postings) == [-1626800, 1626800]
        assert {p.origin for p in merged.postings} == {OBS}
        assert repo.in_transit_halves() == []


def test_replace_posting_account_and_import_postings(database, books) -> None:  # type: ignore[no-untyped-def]
    sav, _, transit, _, food = books
    with database.transaction() as s:
        imp = ImportRepository(s).add(
            sav.id,
            "sep.csv",
            "0" * 64,
            period_start=None,
            period_end=D("2026-09-30"),
            rows_inserted=1,
            hashes_ignored=0,
            closing_balance=100,
            balance_as_of=D("2026-09-30"),
        )
        t = tx("2026-09-03", (sav, -64000, OBS), (transit, 64000, INF), h="x", imp=imp.id)
        JournalRepository(s).add(t)
        counter = next(p for p in JournalRepository(s).get(t.id).postings if p.origin is INF)  # type: ignore[union-attr]
        JournalRepository(s).replace_posting_account(counter.id, food.id, Origin.OWNER)  # type: ignore[arg-type]
        assert {p.account_id for p in JournalRepository(s).get(t.id).postings} == {sav.id, food.id}  # type: ignore[union-attr]
        assert len(JournalRepository(s).postings_from_import(imp.id)) == 2
        got = ImportRepository(s).get(imp.id)
        assert got is not None and (got.closing_balance, got.balance_as_of) == (
            100,
            D("2026-09-30"),
        )


def test_assertions_valuations_and_dismissed_hashes(database, books) -> None:  # type: ignore[no-untyped-def]
    sav, *_ = books
    with database.transaction() as s:
        a = AssertionRepository(s)
        a.add(sav.id, D("2026-09-30"), 23373200, None)
        assert a.exists(sav.id, D("2026-09-30"), 23373200)
        assert not a.exists(sav.id, D("2026-09-30"), 1)
        ValuationRepository(s).add(sav.id, D("2026-09-30"), 5, None)
        assert [v.amount for v in ValuationRepository(s).list_all([sav.id])] == [5]
        repo = JournalRepository(s)
        repo.dismiss(sav.id, ["h9"])
        assert repo.existing_hashes(sav.id, ["h9"]) == {"h9"}


def test_mappings_owner_wins_and_repoint(database) -> None:  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        m = MappingRepository(s)
        m.save_model(
            [MerchantMapping("SWIGGY", "Swiggy", "Expenses:Food:Dining", MappingSource.MODEL, 0.9)]
        )
        m.set_owner("SWIGGY", "Expenses:Gym", "Swiggy")
        m.save_model(
            [MerchantMapping("SWIGGY", "Swiggy", "Expenses:Shopping", MappingSource.MODEL, 0.9)]
        )
        assert m.get_many(["SWIGGY"])["SWIGGY"].label == "Expenses:Gym"
        assert m.repoint("Expenses:Gym", "Expenses:Health") == 1
        assert m.get_many(["SWIGGY"])["SWIGGY"].label == "Expenses:Health"


def test_accounts_update_retire_usage_and_settings(database, books) -> None:  # type: ignore[no-untyped-def]
    sav, _, _, _, food = books
    with database.transaction() as s:
        repo = AccountRepository(s)
        repo.update(sav.id, display_name="Main savings")
        assert repo.get(sav.id).display_name == "Main savings"  # type: ignore[union-attr]
        assert repo.by_path(food.path).id == food.id  # type: ignore[union-attr]
        JournalRepository(s).add(tx("2026-09-03", (sav, -1, OBS), (food, 1, INF)))
        assert repo.usage(food.id).postings == 1
        repo.retire(food.id, D("2026-10-01"))
        assert food.id not in {a.id for a in repo.list_all(AccountRole.CATEGORY)}
        assert food.id in {a.id for a in repo.list_all(AccountRole.CATEGORY, include_retired=True)}
        settings = SettingsRepository(s)
        settings.update(min_cash_buffer=500, monthly_allowance=9000)
        got = settings.get()
        assert (got.min_cash_buffer, got.monthly_allowance, got.setup_completed_at) == (
            500,
            9000,
            None,
        )


def test_migration_0009_upgrades_from_0008_and_refuses_downgrade(admin_engine, pg_url: str) -> None:  # type: ignore[no-untyped-def]
    name = f"walk_{int(time.time() * 1000)}"
    with admin_engine.connect() as c:
        c.execute(text(f"CREATE DATABASE {name}"))
    url = pg_url.rsplit("/", 1)[0] + f"/{name}"
    try:
        cfg = alembic_config(url)
        command.upgrade(cfg, "0008")
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        tables = set(inspect(engine).get_table_names())
        assert {"postings", "assertions", "dismissed_hashes", "import_hashes"} <= tables
        assert not {"events", "spending_plans", "transfer_links", "obligation_rules"} & tables
        with pytest.raises(NotImplementedError):
            command.downgrade(cfg, "0008")
        engine.dispose()
    finally:
        with admin_engine.connect() as c:
            c.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))


def test_concurrent_uploads_serialize(database: Database) -> None:
    order: list[str] = []

    def hold(tag: str) -> None:
        with database.upload_lock():
            order.append(f"{tag}-in")
            time.sleep(0.2)
            order.append(f"{tag}-out")

    a = threading.Thread(target=hold, args=("a",))
    b = threading.Thread(target=hold, args=("b",))
    a.start(), time.sleep(0.05), b.start()
    a.join(), b.join()
    assert order == ["a-in", "a-out", "b-in", "b-out"]
