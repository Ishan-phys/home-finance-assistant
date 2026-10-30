"""Checks on the books themselves."""

from __future__ import annotations

from cfo.core.ids import Id
from cfo.ledger.repositories.transactions import JournalRepository
from sqlalchemy.orm import Session


def verify_books(s: Session) -> list[Id]:
    """Ids of transactions in scope whose postings do not sum to zero. From migration 0011 on the
    database refuses new ones; this finds any written before it."""
    return [t.id for t in JournalRepository(s).list_all() if sum(p.amount for p in t.postings) != 0]
