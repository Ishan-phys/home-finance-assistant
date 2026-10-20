"""Request dependencies shared by the routers."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from cfo.core.errors import NotFoundError
from cfo.core.types import Scope
from cfo.ledger.repositories.people import PeopleRepository
from fastapi import Depends, Request


def _scope_dependency(request: Request, person_id: UUID) -> Scope:
    """The ledger of the person in the path. Nothing under /people/{id} can reach another's."""
    deps = request.app.state.deps
    with deps.db.transaction() as s:
        scope = PeopleRepository(s).scope_of(person_id)
    if scope is None:
        raise NotFoundError(f"unknown person {person_id}")
    return scope


ScopeDep = Annotated[Scope, Depends(_scope_dependency)]
