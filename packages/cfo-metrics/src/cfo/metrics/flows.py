"""What each movement on a real account was: spending, income, a transfer, or money to or from
people.

Every question of the form "which card / account had the most ..." starts here. A transaction
touches a real account (bank, card, loan) on one side and usually a category on the other; the
other side says what happened. Money that moves between the owner's own accounts, or into
money in transit, is a transfer and is never spending or income. The sign is the ledger's: a
negative posting on a real account means money left it, which for a card is a purchase.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from cfo.core.chart import IN_TRANSIT
from cfo.core.ids import Id
from cfo.core.types import Account, AccountKind, AccountRole, Heading, Transaction


class Bucket(StrEnum):
    SPENDING = "spending"  # an expense category, other than money to people
    PEOPLE = "people"  # money to or from friends and family
    INCOME = "income"  # salary, interest, cashback
    TRANSFER = "transfer"  # between the owner's own accounts, or money in transit
    OTHER = "other"  # opening balances and revaluation


@dataclass(frozen=True, slots=True)
class Flow:
    """One posting on a real account, with what the other side says it was."""

    date: date
    payee: str
    narration: str
    account_id: Id  # the real account
    amount: int  # signed as the ledger holds it: negative means money left this account
    bucket: Bucket
    counterpart: Account | None  # the account on the other side that decided the bucket

    @property
    def out(self) -> bool:
        return self.amount < 0


def _bucket(a: Account) -> Bucket:
    if a.role is AccountRole.REAL:
        return Bucket.TRANSFER
    if a.role is AccountRole.SYSTEM:
        return Bucket.TRANSFER if a.path == IN_TRANSIT else Bucket.OTHER
    if a.kind is AccountKind.EXPENSE:
        return Bucket.PEOPLE if a.heading is Heading.PEOPLE else Bucket.SPENDING
    if a.kind is AccountKind.INCOME:
        return Bucket.PEOPLE if a.heading is Heading.PEOPLE else Bucket.INCOME
    return Bucket.OTHER


def flows(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    start: date | None = None,
    end: date | None = None,
) -> list[Flow]:
    """Every real-account posting dated within [start, end], classified. When the other side of a
    transaction has several postings, the largest decides; transactions that split across
    kinds are rare and are filed under their biggest part."""
    by_id = {a.id: a for a in accounts}
    out: list[Flow] = []
    for t in transactions:
        if (start and t.date < start) or (end and t.date > end):
            continue
        for p in t.postings:
            own = by_id.get(p.account_id)
            if own is None or own.role is not AccountRole.REAL or p.amount == 0:
                continue
            others = [
                (abs(q.amount), str(q.account_id), by_id[q.account_id])
                for q in t.postings
                if q is not p and q.account_id in by_id
            ]
            if not others:
                continue
            counterpart = max(others, key=lambda o: (o[0], o[1]))[2]
            out.append(
                Flow(
                    t.date,
                    t.payee,
                    t.narration,
                    own.id,
                    p.amount,
                    _bucket(counterpart),
                    counterpart,
                )
            )
    return out
