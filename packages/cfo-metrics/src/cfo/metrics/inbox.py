"""Everything that needs the owner: rows without a category, own-account moves whose other side
has not been seen, statements the ledger does not agree with, and card bills not yet paid."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from cfo.core.chart import IN_TRANSIT, UNCATEGORIZED_IN, UNCATEGORIZED_OUT
from cfo.core.ids import Id
from cfo.core.types import (
    Account,
    AccountRole,
    AccountType,
    Assertion,
    ImportRecord,
    Origin,
    Transaction,
)
from cfo.metrics.reconcile import gaps

Kind = Literal["uncategorized", "unpaired", "gap", "card_due"]


@dataclass(frozen=True, slots=True)
class InboxItem:
    kind: Kind
    amount: int  # positive
    date: date
    account_id: Id | None = None  # the owner's real account the item is about
    transaction_id: Id | None = None


def inbox(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    assertions: Sequence[Assertion],
    imports: Sequence[ImportRecord],
) -> tuple[InboxItem, ...]:
    by_path = {a.path: a.id for a in accounts}
    real = {a.id for a in accounts if a.role is AccountRole.REAL}
    uncategorized = {by_path.get(UNCATEGORIZED_OUT), by_path.get(UNCATEGORIZED_IN)} - {None}
    transit = by_path.get(IN_TRANSIT)
    items: list[InboxItem] = []
    for t in transactions:
        observed = [p for p in t.postings if p.origin is Origin.OBSERVED and p.account_id in real]
        home = observed[0] if len(observed) == 1 else None
        for p in t.postings:
            if p.account_id in uncategorized and home is not None:
                items.append(
                    InboxItem("uncategorized", abs(p.amount), t.date, home.account_id, t.id)
                )
            elif p.account_id == transit and p.origin is Origin.INFERRED and home is not None:
                items.append(InboxItem("unpaired", abs(home.amount), t.date, home.account_id, t.id))
    for g in gaps(accounts, transactions, assertions):
        items.append(InboxItem("gap", abs(g.difference), g.as_of, g.account_id))
    cards = {a.id for a in accounts if a.type is AccountType.CREDIT_CARD}
    latest: dict[Id, ImportRecord] = {}
    for imp in imports:
        if imp.account_id in cards and imp.period_end is not None:
            held = latest.get(imp.account_id)
            if held is None or (held.period_end is not None and imp.period_end >= held.period_end):
                latest[imp.account_id] = imp
    for card_id, imp in latest.items():
        if not imp.amount_due or imp.period_end is None:
            continue
        # A payment is money arriving on the card from one of the owner's accounts (or in
        # transit from one): a refund or cashback credit is not.
        paid = any(
            p.account_id == card_id
            and p.amount > 0
            and p.origin is Origin.OBSERVED
            and t.date >= imp.period_end
            and any(
                q.account_id in real or q.account_id == transit for q in t.postings if q is not p
            )
            for t in transactions
            for p in t.postings
        )
        if not paid:
            items.append(
                InboxItem("card_due", imp.amount_due, imp.due_date or imp.period_end, card_id)
            )
    items.sort(key=lambda i: (i.date, i.kind), reverse=True)
    return tuple(items)
