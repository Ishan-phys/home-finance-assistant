"""Occurrence counting and deduplication hashes (spec 3.3)."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from cfo.core.ids import Id
from cfo.parse.base import CanonicalRow


@dataclass(frozen=True, slots=True)
class HashedRow:
    row: CanonicalRow
    occurrence: int
    dedup_hash: str


def dedup_hash(posted: date, amount: int, account_id: Id, description: str, occurrence: int) -> str:
    text = f"{posted.isoformat()}|{amount}|{account_id}|{description}|{occurrence}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_rows(rows: Sequence[CanonicalRow], account_id: Id) -> list[HashedRow]:
    """Occurrence counts rows in this file sharing date, amount, and description, in file order."""
    seen: Counter[tuple[date, int, str]] = Counter()
    out: list[HashedRow] = []
    for row in rows:
        key = (row.date, row.amount, row.raw_description)
        seen[key] += 1
        n = seen[key]
        out.append(
            HashedRow(row, n, dedup_hash(row.date, row.amount, account_id, row.raw_description, n))
        )
    return out
