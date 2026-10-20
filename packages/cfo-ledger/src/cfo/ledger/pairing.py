"""Pairing own-account halves: a debit on one account and a credit on another that are the two
sides of one movement, each waiting on money in transit."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from cfo.core.ids import Id


@dataclass(frozen=True, slots=True)
class Half:
    tx_id: Id
    account_id: Id  # the observed account
    date: date
    amount: int  # the money-in-transit posting's amount


# Card payments and own-account transfers can take a couple of days to land on the other side.
PAIR_WINDOW_DAYS = 3


def find_pairs(halves: Sequence[Half], window_days: int = PAIR_WINDOW_DAYS) -> list[tuple[Id, Id]]:
    """Pairs of halves that are one movement: equal and opposite amounts on different accounts
    within the window. Each half is used once; the closest dates win, then the earlier date,
    then the ids, so the result does not depend on the order the halves arrive in. Each pair
    is (the side money left, the side it arrived)."""
    candidates = []
    ordered = sorted(halves, key=lambda h: str(h.tx_id))
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if a.amount != -b.amount or a.amount == 0 or a.account_id == b.account_id:
                continue
            gap = abs((a.date - b.date).days)
            if gap > window_days:
                continue
            out, into = (a, b) if a.amount > 0 else (b, a)
            candidates.append(
                (gap, min(a.date, b.date), str(out.tx_id), str(into.tx_id), out, into)
            )
    used: set[Id] = set()
    pairs: list[tuple[Id, Id]] = []
    for *_, out, into in sorted(candidates, key=lambda c: c[:4]):
        if out.tx_id in used or into.tx_id in used:
            continue
        used |= {out.tx_id, into.tx_id}
        pairs.append((out.tx_id, into.tx_id))
    return pairs
