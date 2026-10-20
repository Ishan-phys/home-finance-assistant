"""Setup: the ledger's defaults, the owner's accounts and their own categories (spec §3, §5.0)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from cfo.core.chart import DEFAULT_CATEGORIES, OPENING, SYSTEM_ACCOUNTS
from cfo.core.errors import CategoryInUse, ConflictError, InvalidInput, SetupRequired
from cfo.core.types import (
    AccountRole,
    AccountType,
    Direction,
    Group,
    MappingSource,
    MerchantMapping,
    Origin,
)
from cfo.ledger.repositories.accounts import AccountRepository, SettingsRepository
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.transactions import JournalRepository, MappingRepository
from cfo.ledger.setup import (
    AccountInput,
    CategoryInput,
    add_account,
    add_category,
    complete_setup,
    create_ledger_defaults,
    delete_account,
    delete_category,
    edit_account,
    edit_category,
    is_set_up,
    merge_category,
    retire_category,
)
from cfo.metrics.balances import balance

TODAY = date(2026, 10, 20)


def test_new_ledger_has_defaults_and_system_accounts(database: Database) -> None:
    with database.transaction() as s:
        repo = AccountRepository(s)
        cats = repo.list_all(AccountRole.CATEGORY)
        system = repo.list_all(AccountRole.SYSTEM)
        assert sorted(a.path for a in cats) == sorted(c.path for c in DEFAULT_CATEGORIES)
        assert sorted(a.path for a in system) == sorted(p for p, _ in SYSTEM_ACCOUNTS)
        dining = repo.by_path("Expenses:Food:Dining")
        assert dining is not None and dining.description == "Restaurants, cafés, food delivery"
        create_ledger_defaults(s)  # idempotent
        assert len(repo.list_all()) == len(cats) + len(system)


def test_add_account_builds_path_and_group(database: Database) -> None:
    with database.transaction() as s:
        a = add_account(
            s, AccountInput(AccountType.SAVINGS, "HDFC", "HDFC Savings"), TODAY, "hdfc_bank"
        )
        b = add_account(
            s, AccountInput(AccountType.SAVINGS, "HDFC", "HDFC Savings"), TODAY, "hdfc_bank"
        )
        assert a.path == "Assets:Bank:HDFC:HDFC-Savings" and b.path.endswith("HDFC-Savings-2")
        assert (a.group, a.binding, a.role, a.opened_on) == (
            Group.LIQUID,
            "hdfc_bank",
            AccountRole.REAL,
            TODAY,
        )
        renamed = edit_account(s, a.id, name="Main", institution=None, cycle_day=None)
        assert renamed.display_name == "Main" and renamed.path == a.path
        with pytest.raises(InvalidInput):
            add_account(s, AccountInput(AccountType.SAVINGS, "HDFC", "  "), TODAY)


def test_manual_account_posts_opening_value(database: Database) -> None:
    with database.transaction() as s:
        fd = add_account(
            s,
            AccountInput(
                AccountType.FIXED_DEPOSIT,
                "SBI",
                "SBI FD",
                opening_value=50000000,
                opening_date=date(2026, 4, 1),
            ),
            TODAY,
        )
        (t,) = JournalRepository(s).list_all([fd.id])
        opening = AccountRepository(s).by_path(OPENING)
        assert opening is not None and t.source == "system" and t.date == date(2026, 4, 1)
        assert {(p.account_id, p.amount, p.origin) for p in t.postings} == {
            (fd.id, 50000000, Origin.SYSTEM),
            (opening.id, -50000000, Origin.SYSTEM),
        }
        assert balance(fd.id, JournalRepository(s).list_all()) == 50000000
        with pytest.raises(InvalidInput):
            add_account(s, AccountInput(AccountType.GOLD, "Home", "Gold"), TODAY)


def test_add_category_requires_description_and_unique_name(database: Database) -> None:
    with database.transaction() as s:
        gym = add_category(s, CategoryInput("Gym", Direction.OUT, "Memberships and classes"))
        assert (gym.path, gym.role, gym.direction) == (
            "Expenses:Gym",
            AccountRole.CATEGORY,
            Direction.OUT,
        )
        food = AccountRepository(s).by_path("Expenses:Food")
        dining = AccountRepository(s).by_path("Expenses:Food:Dining")
        assert food is None and dining is not None
        snacks = add_category(
            s, CategoryInput("Snacks", Direction.OUT, "Chips", parent_id=dining.id)
        )
        assert snacks.path == "Expenses:Food:Dining:Snacks"
        with pytest.raises(InvalidInput):
            add_category(s, CategoryInput("Pets", Direction.OUT, "   "))
        with pytest.raises(ConflictError):
            add_category(s, CategoryInput("gym", Direction.OUT, "again"))
        with pytest.raises(InvalidInput):  # a parent of the other direction
            salary = AccountRepository(s).by_path("Income:Salary")
            add_category(s, CategoryInput("Bonus", Direction.OUT, "x", parent_id=salary.id))  # type: ignore[union-attr]
        edited = edit_category(s, gym.id, name="Fitness", description="Gyms and studios")
        assert (edited.display_name, edited.description, edited.path) == (
            "Fitness",
            "Gyms and studios",
            "Expenses:Gym",
        )


def test_merge_moves_postings_and_mappings(database: Database) -> None:
    with database.transaction() as s:
        sav = add_account(
            s, AccountInput(AccountType.SAVINGS, "HDFC", "Savings"), TODAY, "hdfc_bank"
        )
        gym = add_category(s, CategoryInput("Gym", Direction.OUT, "Memberships"))
        health = AccountRepository(s).by_path("Expenses:Health")
        assert health is not None
        from cfo.testing.helpers import INF, OBS, txn

        repo = JournalRepository(s)
        for day in ("2026-09-03", "2026-09-10"):
            repo.add(txn(day, (sav, -150000, OBS), (gym, 150000, INF), narration="CULTFIT"))
        MappingRepository(s).save_model(
            [MerchantMapping("CULTFIT", "Cultfit", gym.path, MappingSource.MODEL, 0.9)]
        )
        moved = merge_category(s, gym.id, health.id, TODAY)
        assert moved == 2
        assert MappingRepository(s).get_many(["CULTFIT"])["CULTFIT"].label == health.path
        assert AccountRepository(s).get(gym.id).retired_on == TODAY  # type: ignore[union-attr]
        assert balance(health.id, repo.list_all()) == 300000
        salary = AccountRepository(s).by_path("Income:Salary")
        with pytest.raises(InvalidInput):
            merge_category(s, health.id, salary.id, TODAY)  # type: ignore[union-attr]


def test_cannot_delete_used_category_or_touch_system_accounts(database: Database) -> None:
    with database.transaction() as s:
        sav = add_account(s, AccountInput(AccountType.SAVINGS, "HDFC", "Savings"), TODAY)
        travel = AccountRepository(s).by_path("Expenses:Travel")
        assert travel is not None
        from cfo.testing.helpers import INF, OBS, txn

        JournalRepository(s).add(txn("2026-09-03", (sav, -1, OBS), (travel, 1, INF)))
        with pytest.raises(CategoryInUse):
            delete_category(s, travel.id)
        unused = add_category(s, CategoryInput("Pets", Direction.OUT, "Vet and food"))
        delete_category(s, unused.id)
        assert AccountRepository(s).get(unused.id) is None
        opening = AccountRepository(s).by_path(OPENING)
        for action in (
            lambda: retire_category(s, opening.id, TODAY),  # type: ignore[union-attr]
            lambda: delete_category(s, opening.id),  # type: ignore[union-attr]
            lambda: edit_category(s, opening.id, name="x"),  # type: ignore[union-attr]
        ):
            with pytest.raises(InvalidInput):
                action()
        dining = AccountRepository(s).by_path("Expenses:Food:Dining")
        add_category(s, CategoryInput("Snacks", Direction.OUT, "Chips", parent_id=dining.id))  # type: ignore[union-attr]
        with pytest.raises(ConflictError):
            retire_category(s, dining.id, TODAY)  # type: ignore[union-attr]
        delete_account(s, sav.id)  # an account goes with everything on it
        assert AccountRepository(s).get(sav.id) is None


def test_setup_requires_an_account(database: Database) -> None:
    now = datetime(2026, 10, 20, 9, tzinfo=UTC)
    with database.transaction() as s:
        assert not is_set_up(s)
        with pytest.raises(SetupRequired):
            complete_setup(s, now)
        add_account(s, AccountInput(AccountType.CREDIT_CARD, "HDFC", "Card"), TODAY, "hdfc_card")
        assert is_set_up(s)
        complete_setup(s, now)
        assert SettingsRepository(s).get().setup_completed_at == now


def test_a_ledger_from_before_the_upgrade_gets_its_defaults(database: Database) -> None:
    from cfo.ledger.repositories.models import AccountRow
    from sqlalchemy import delete

    with database.transaction() as s:  # final review I1: 0009 dropped accounts but kept the ledger
        s.execute(delete(AccountRow))
        assert AccountRepository(s).list_all() == []
        add_account(s, AccountInput(AccountType.SAVINGS, "HDFC", "Savings"), TODAY, "hdfc_bank")
        paths = {a.path for a in AccountRepository(s).list_all()}
        assert "Expenses:Uncategorized" in paths and "Assets:InTransit" in paths
        assert {c.path for c in DEFAULT_CATEGORIES} <= paths


def test_retiring_a_category_forgets_what_pointed_at_it(database: Database) -> None:
    with database.transaction() as s:  # final review I3
        gym = add_category(s, CategoryInput("Gym", Direction.OUT, "Memberships"))
        MappingRepository(s).save_model(
            [MerchantMapping("CULTFIT", "Cultfit", gym.path, MappingSource.MODEL, 0.9)]
        )
        MappingRepository(s).set_owner("MY GYM", gym.path, "My Gym")
        retire_category(s, gym.id, TODAY)
        assert MappingRepository(s).get_many(["CULTFIT", "MY GYM"]) == {}
