"""People, ledgers, households, and scope (spec 3.10)."""

from __future__ import annotations

from datetime import date

import pytest
from cfo.core.ids import new_id
from cfo.core.types import Account, AccountKind, AccountRole, Scope
from cfo.ledger.repositories.accounts import (
    AccountRepository,
    RedactionTermRepository,
    SettingsRepository,
)
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.people import HouseholdRepository, PeopleRepository
from cfo.ledger.repositories.scope import ScopeMissingError

D = date.fromisoformat


def two_people(database: Database):  # type: ignore[no-untyped-def]
    with database.transaction() as s:
        people = PeopleRepository(s)
        asha, a_ledger = people.create("Asha Rao", ["Rao Family"])
        ben, b_ledger = people.create("Ben Mills")
    return (asha, Scope.of(a_ledger.id)), (ben, Scope.of(b_ledger.id))


def cat(path: str) -> Account:
    return Account(new_id(), path, AccountKind.EXPENSE, AccountRole.CATEGORY, path)


def test_creating_a_person_creates_a_ledger_and_seeds_redaction_terms_from_the_name(
    database: Database,
) -> None:
    (_, a_scope), (_, b_scope) = two_people(database)
    with database.transaction(a_scope) as s:
        terms = RedactionTermRepository(s).list_all()
        assert SettingsRepository(s).get().min_cash_buffer == 0
        assert len(SettingsRepository(s).salt()) == 32
    assert terms == ["Asha Rao", "Asha", "Rao", "Rao Family", "Family"]
    with database.transaction(b_scope) as s:
        other = SettingsRepository(s).salt()
    with database.transaction(a_scope) as s:
        assert SettingsRepository(s).salt() != other
    with database.transaction() as s, pytest.raises(ValueError, match="needs a name"):
        PeopleRepository(s).create("   ")


def test_two_ledgers_never_see_each_other(database: Database) -> None:
    (_, a_scope), (_, b_scope) = two_people(database)
    with database.transaction(a_scope) as s:
        mine = AccountRepository(s).add(cat("Expenses:Mine"))
    with database.transaction(b_scope) as s:
        assert AccountRepository(s).get(mine.id) is None
        assert mine.id not in {a.id for a in AccountRepository(s).list_all()}


def test_a_repository_cannot_be_built_without_a_scope(database: Database) -> None:
    database.default_scope = None
    with database.transaction() as s, pytest.raises(ScopeMissingError):
        AccountRepository(s)


def test_a_write_needs_exactly_one_ledger(database: Database) -> None:
    (_, a_scope), (_, b_scope) = two_people(database)
    with database.transaction(a_scope | b_scope) as s, pytest.raises(ValueError):
        AccountRepository(s).add(cat("Expenses:Both"))


def test_ids_are_uuid_v7(database: Database) -> None:
    with database.transaction() as s:
        a = AccountRepository(s).add(cat("Expenses:One"))
    assert a.id.version == 7


def test_household_scope_and_membership(database: Database) -> None:
    (asha, a_scope), (ben, b_scope) = two_people(database)
    with database.transaction() as s:
        homes = HouseholdRepository(s)
        home = homes.create("Home")
        homes.add_member(home.id, asha.id, on=D("2026-01-01"))
        homes.add_member(home.id, ben.id, on=D("2026-01-01"), visibility="balances_only")
        assert homes.scope_of(home.id) == a_scope  # balances-only members are left out
        homes.leave(home.id, asha.id, on=D("2026-06-01"))
        assert homes.scope_of(home.id) == Scope(frozenset())


def test_unknown_person_has_no_scope(database: Database) -> None:
    with database.transaction() as s:
        assert PeopleRepository(s).scope_of(new_id()) is None
