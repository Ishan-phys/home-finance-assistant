"""Finding movements: by payee text, category, account, direction and period.

Answers "how much did I spend on Swiggy", "my biggest expenses in September", "what came into
my savings account". Transfers between the owner's own accounts are left out unless asked for,
because a card bill payment is not spending.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import date
from typing import Literal

from cfo.core.dates import month_key
from cfo.core.ids import Id
from cfo.core.types import Account, Transaction
from cfo.metrics.flows import Bucket, Flow, flows

Direction = Literal["out", "in", "any"]


def _category_matches(f: Flow, wanted: str) -> bool:
    if f.counterpart is None:
        return False
    needle = wanted.strip().casefold()
    names = [f.counterpart.display_name, *f.counterpart.path.split(":")]
    return any(needle in n.casefold() for n in names)


def find_flows(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    start: date | None,
    end: date | None,
    *,
    text: str | None = None,
    direction: Direction = "out",
    category: str | None = None,
    account_ids: Collection[Id] | None = None,
    include_transfers: bool = False,
) -> list[Flow]:
    needle = text.strip().casefold() if text and text.strip() else None
    found: list[Flow] = []
    for f in flows(accounts, transactions, start, end):
        if direction == "out" and not f.out or direction == "in" and f.out:
            continue
        if f.bucket is Bucket.OTHER:  # opening balances and revaluation are not payments
            continue
        if f.bucket is Bucket.TRANSFER and not include_transfers:
            continue
        if account_ids is not None and f.account_id not in account_ids:
            continue
        if needle and needle not in f.payee.casefold() and needle not in f.narration.casefold():
            continue
        if category and not _category_matches(f, category):
            continue
        found.append(f)
    return found


def by_month(matches: Sequence[Flow]) -> list[tuple[str, int, int]]:
    """(month, total paise, count) for each month with a match, oldest first."""
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for f in matches:
        slot = totals[month_key(f.date)]
        slot[0] += abs(f.amount)
        slot[1] += 1
    return [(m, v[0], v[1]) for m, v in sorted(totals.items())]


def largest_first(matches: Sequence[Flow]) -> list[Flow]:
    return sorted(matches, key=lambda f: (-abs(f.amount), f.date, f.payee))


def latest_first(matches: Sequence[Flow]) -> list[Flow]:
    return sorted(matches, key=lambda f: (f.date, abs(f.amount)), reverse=True)
