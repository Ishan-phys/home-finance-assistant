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
    Assertion,
    ImportRecord,
    Origin,
    Transaction,
)
from cfo.metrics.card_payments import card_bills
from cfo.metrics.reconcile import gaps

Kind = Literal["uncategorized", "unpaired", "gap", "card_due"]


@dataclass(frozen=True, slots=True)
class InboxItem:
    kind: Kind
    amount: int  # positive
    date: date
    account_id: Id | None = None  # the owner's real account the item is about
    transaction_id: Id | None = None
    due: int | None = None  # a card bill: the statement's full amount, when only part is left


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
    for bill in card_bills(accounts, transactions, imports):
        if bill.remaining:
            items.append(
                InboxItem("card_due", bill.remaining, bill.due_date, bill.card_id, due=bill.due)
            )
    items.sort(key=lambda i: (i.date, i.kind), reverse=True)
    return tuple(items)
