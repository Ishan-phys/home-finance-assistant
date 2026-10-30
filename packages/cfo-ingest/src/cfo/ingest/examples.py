"""The owner's past decisions as examples for the categorizer."""

from __future__ import annotations

from cfo.categorize.labels import Way
from cfo.categorize.port import Example
from cfo.core.chart import IN_TRANSIT
from cfo.ledger.repositories.transactions import MappingRepository
from sqlalchemy.orm import Session


def owner_examples(s: Session) -> list[Example]:
    """What the owner has categorized by hand, oldest first. Narrations are the stored redacted
    ones, so the person tokens are the same ones the model is asked about."""
    out: list[Example] = []
    for m in MappingRepository(s).list_owner():
        way: Way | None
        if m.label == IN_TRANSIT:
            way = None
        else:
            way = "credit" if m.label.startswith("Income:") else "debit"
        out.append(Example(m.lookup_key, way, m.label))
    return out
