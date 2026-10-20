"""Scope: the ledgers a repository may touch (spec 3.10 rule 1).

A repository cannot be built without one. It comes from the transaction (`Database.transaction`
puts it on the session) or is passed explicitly. A scope of several ledgers reads across them,
for a household view; a write needs exactly one.
"""

from __future__ import annotations

from typing import Any

from cfo.core.ids import Id
from cfo.core.types import Scope
from sqlalchemy.orm import Session

SCOPE_KEY = "scope"


class ScopeMissingError(RuntimeError):
    """A repository was built with no scope. This is a bug in the caller, never a user error."""


def scope_of(session: Session, explicit: Scope | None = None) -> Scope:
    found = explicit or session.info.get(SCOPE_KEY)
    if not isinstance(found, Scope):
        raise ScopeMissingError("open the transaction with a scope: db.transaction(scope)")
    return found


class ScopedRepository:
    def __init__(self, session: Session, scope: Scope | None = None) -> None:
        self.s = session
        self.scope = scope_of(session, scope)

    @property
    def ledger_id(self) -> Id:
        """The ledger a write goes to. Raises for a scope of more than one ledger."""
        return self.scope.single()

    def in_scope(self, column: Any) -> Any:
        return column.in_(self.scope.ledger_ids)
