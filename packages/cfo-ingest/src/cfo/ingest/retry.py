"""Retry categorization of Uncategorized rows without reimporting (spec 4.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from cfo.categorize.categorizer import ModelClient
from cfo.categorize.port import Categorizer, Item, as_categorizer
from cfo.core.types import Scope
from cfo.ingest.masking import build_masker
from cfo.ingest.upload import ledger_labels
from cfo.ledger.journal import apply_to_uncategorized, uncategorized_rows
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.transactions import MappingRepository


@dataclass(frozen=True, slots=True)
class RetryResult:
    rows_updated: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


def retry_categorization(
    db: Database, client: Categorizer | ModelClient, scope: Scope | None = None
) -> RetryResult:
    """Categorize Uncategorized rows again without reimporting. Owner mappings are kept."""
    with db.upload_lock():
        with db.transaction(scope) as s:
            rows = uncategorized_rows(s)
            directions: dict[str, Literal["debit", "credit"]] = {
                narration: ("debit" if amount < 0 else "credit") for narration, amount in rows
            }
            known = MappingRepository(s).get_many(directions)
            masker = build_masker(s)
            labels = ledger_labels(s)
        todo = [d for d in directions if d not in known]
        categorizer = as_categorizer(client, masker)
        assert categorizer is not None
        result = categorizer.categorize([Item(d, directions[d]) for d in todo], labels)
        with db.transaction(scope) as s:
            MappingRepository(s).save_model(result.mappings.values())
            updated = apply_to_uncategorized(s, {**known, **result.mappings})
        return RetryResult(updated, result.warnings)
