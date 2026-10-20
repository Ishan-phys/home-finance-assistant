"""Account balances: the sum of an account's postings up to a date."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from cfo.core.ids import Id
from cfo.core.types import Transaction


def balances_at(transactions: Iterable[Transaction], as_of: date | None = None) -> dict[Id, int]:
    """Every account's balance on `as_of` (inclusive), or over all time when it is None."""
    out: dict[Id, int] = defaultdict(int)
    for t in transactions:
        if as_of is None or t.date <= as_of:
            for p in t.postings:
                out[p.account_id] += p.amount
    return out


def balance(account_id: Id, transactions: Iterable[Transaction], as_of: date | None = None) -> int:
    return balances_at(transactions, as_of).get(account_id, 0)
