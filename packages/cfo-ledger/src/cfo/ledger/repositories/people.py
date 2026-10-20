"""People, their ledgers, and households (spec 3.10).

These repositories are not scoped: they are how a scope is found. A person is created with a
name, which also seeds the redaction terms of their new ledger, so their own name never reaches a
statement row or a model request.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from datetime import date

from cfo.core.ids import Id, new_id
from cfo.core.types import Household, Ledger, Person, Scope
from cfo.ledger.repositories.models import (
    HouseholdMemberRow,
    HouseholdRow,
    LedgerRow,
    LedgerSettingsRow,
    PersonRow,
    RedactionTermRow,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def name_terms(*names: str) -> list[str]:
    """A name as redaction terms: the whole name, then each word of it."""
    terms: list[str] = []
    seen: set[str] = set()
    for name in names:
        name = " ".join(name.split())
        if not name:
            continue
        for term in [name, *re.findall(r"[^\W\d_]{2,}", name)]:
            if term.casefold() not in seen:
                seen.add(term.casefold())
                terms.append(term)
    return terms


class PeopleRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create(self, name: str, family_names: Sequence[str] = ()) -> tuple[Person, Ledger]:
        """Create a person and, with them, their ledger, settings, and redaction terms."""
        name = " ".join(name.split())
        if not name:
            raise ValueError("a person needs a name")
        person = PersonRow(id=new_id(), name=name)
        self.s.add(person)
        self.s.flush()
        ledger = LedgerRow(id=new_id(), person_id=person.id, pseudonym_salt=os.urandom(32))
        self.s.add(ledger)
        self.s.flush()
        self.s.add(LedgerSettingsRow(ledger_id=ledger.id, min_cash_buffer=0))
        for term in name_terms(name, *family_names):
            self.s.add(RedactionTermRow(id=new_id(), ledger_id=ledger.id, term=term))
        self.s.flush()
        from cfo.ledger.setup import create_ledger_defaults  # noqa: PLC0415  (service on top)

        create_ledger_defaults(self.s, Scope.of(ledger.id))
        return Person(person.id, person.name), Ledger(ledger.id, person.id)

    def list_all(self) -> list[tuple[Person, Ledger]]:
        q = select(PersonRow, LedgerRow).join(LedgerRow, LedgerRow.person_id == PersonRow.id)
        return [
            (Person(p.id, p.name), Ledger(led.id, p.id))
            for p, led in self.s.execute(q.order_by(PersonRow.id))
        ]

    def get(self, person_id: Id) -> tuple[Person, Ledger] | None:
        q = (
            select(PersonRow, LedgerRow)
            .join(LedgerRow, LedgerRow.person_id == PersonRow.id)
            .where(PersonRow.id == person_id)
        )
        row = self.s.execute(q).first()
        return (
            None if row is None else (Person(row[0].id, row[0].name), Ledger(row[1].id, person_id))
        )

    def scope_of(self, person_id: Id) -> Scope | None:
        found = self.get(person_id)
        return None if found is None else Scope.of(found[1].id)

    def any(self) -> bool:
        return self.s.scalars(select(PersonRow.id).limit(1)).first() is not None


class HouseholdRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create(self, name: str) -> Household:
        row = HouseholdRow(id=new_id(), name=name.strip())
        self.s.add(row)
        self.s.flush()
        return Household(row.id, row.name)

    def add_member(
        self,
        household_id: Id,
        person_id: Id,
        *,
        on: date,
        role: str = "member",
        visibility: str = "full",
    ) -> None:
        """A person is in at most one household at a time; the database refuses a second."""
        self.s.add(
            HouseholdMemberRow(
                household_id=household_id,
                person_id=person_id,
                from_date=on,
                role=role,
                visibility=visibility,
            )
        )
        self.s.flush()

    def leave(self, household_id: Id, person_id: Id, *, on: date) -> None:
        row = self.s.scalars(
            select(HouseholdMemberRow).where(
                HouseholdMemberRow.household_id == household_id,
                HouseholdMemberRow.person_id == person_id,
                HouseholdMemberRow.until_date.is_(None),
            )
        ).first()
        if row is not None:
            row.until_date = on
            self.s.flush()

    def scope_of(self, household_id: Id, *, on: date | None = None) -> Scope:
        """Every ledger of the household's current members. Members who share only balances
        are left out until that sharing is built (spec 3.10 rule 10)."""
        q = (
            select(LedgerRow.id)
            .join(HouseholdMemberRow, HouseholdMemberRow.person_id == LedgerRow.person_id)
            .where(
                HouseholdMemberRow.household_id == household_id,
                HouseholdMemberRow.until_date.is_(None),
                HouseholdMemberRow.visibility == "full",
            )
        )
        return Scope(frozenset(self.s.scalars(q)))

    def matching_scope(self, ledger_id: Id) -> Scope:
        """The ledgers a transfer from this ledger may be matched against: its own, plus those of
        the other current members of its household (spec 3.10 rule 4)."""
        household_id = self.s.scalars(
            select(HouseholdMemberRow.household_id)
            .join(LedgerRow, LedgerRow.person_id == HouseholdMemberRow.person_id)
            .where(LedgerRow.id == ledger_id, HouseholdMemberRow.until_date.is_(None))
        ).first()
        if household_id is None:
            return Scope.of(ledger_id)
        return self.scope_of(household_id) | Scope.of(ledger_id)
