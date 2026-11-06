"""Credit card bills and the payments made to them: how much of the latest statement is still due,
and which cards a row of money leaving a bank account could have paid. Pure functions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from cfo.core.chart import IN_TRANSIT
from cfo.core.ids import Id
from cfo.core.types import (
    Account,
    AccountRole,
    AccountType,
    Group,
    ImportRecord,
    Origin,
    Transaction,
)
from cfo.metrics.balances import balances_at


@dataclass(frozen=True, slots=True)
class CardBill:
    card_id: Id
    due: int  # the statement's amount due, positive paise
    remaining: int  # what the payments since the statement have not covered, never negative
    due_date: date


@dataclass(frozen=True, slots=True)
class CardChoice:
    account_id: Id
    owed: int  # positive paise the card currently owes
    suggested: bool  # the payment equals what the card owes, or what is left of its bill
    current: bool  # the row is already recorded as a payment to this card


def _is_card(account: Account | None) -> bool:
    return (
        account is not None
        and account.role is AccountRole.REAL
        and account.type is AccountType.CREDIT_CARD
    )


def card_bills(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    imports: Sequence[ImportRecord],
) -> tuple[CardBill, ...]:
    """The latest statement of each card, less the payments dated on or after its end date. A
    payment is money arriving on the card from one of the owner's accounts, or in transit from
    one, whether the statement has shown it yet or the owner recorded it: a refund or a cashback
    credit is not."""
    by_path = {a.path: a.id for a in accounts}
    real = {a.id for a in accounts if a.role is AccountRole.REAL}
    transit = by_path.get(IN_TRANSIT)
    cards = {a.id for a in accounts if _is_card(a)}
    latest: dict[Id, ImportRecord] = {}
    for imp in imports:
        if imp.account_id in cards and imp.period_end is not None:
            held = latest.get(imp.account_id)
            if held is None or (held.period_end is not None and imp.period_end >= held.period_end):
                latest[imp.account_id] = imp
    bills = []
    for card_id, imp in latest.items():
        if not imp.amount_due or imp.period_end is None:
            continue
        paid = sum(
            p.amount
            for t in transactions
            if t.date >= imp.period_end
            for p in t.postings
            if p.account_id == card_id
            and p.amount > 0
            and p.origin in (Origin.OBSERVED, Origin.OWNER)
            and any(
                q.account_id in real or q.account_id == transit for q in t.postings if q is not p
            )
        )
        bills.append(
            CardBill(
                card_id,
                imp.amount_due,
                max(0, imp.amount_due - paid),
                imp.due_date or imp.period_end,
            )
        )
    return tuple(bills)


def payable_amount(accounts: Sequence[Account], tx: Transaction) -> int | None:
    """Positive paise when the row can be recorded as a card payment: money that left a bank or
    cash account, whose other side is still a guess (a category, money in transit,
    uncategorized) or is already recorded as a payment to a card, so a wrong card can be changed.
    None for anything else, such as a row already matched to a card's own statement."""
    by_id = {a.id: a for a in accounts}
    observed = [p for p in tx.postings if p.origin is Origin.OBSERVED]
    others = [p for p in tx.postings if p.origin is not Origin.OBSERVED]
    if len(tx.postings) != 2 or len(observed) != 1 or len(others) != 1:
        return None
    source = by_id.get(observed[0].account_id)
    dest = by_id.get(others[0].account_id)
    if source is None or source.role is not AccountRole.REAL or source.group is not Group.LIQUID:
        return None
    if observed[0].amount >= 0 or dest is None:
        return None
    if dest.role is AccountRole.REAL and not (_is_card(dest) and others[0].origin is Origin.OWNER):
        return None
    return -observed[0].amount


def card_choices(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    imports: Sequence[ImportRecord],
    tx: Transaction,
) -> tuple[CardChoice, ...]:
    """The active cards a row could have paid, the likeliest first. Empty when the row cannot be
    a card payment."""
    amount = payable_amount(accounts, tx)
    if amount is None:
        return ()
    held = balances_at(transactions)
    remaining = {b.card_id: b.remaining for b in card_bills(accounts, transactions, imports)}
    recorded = {p.account_id for p in tx.postings if p.origin is Origin.OWNER}
    choices = []
    for a in accounts:
        if not _is_card(a) or not a.active:
            continue
        owed = max(0, -held.get(a.id, 0))
        choices.append(
            (
                a.display_name,
                CardChoice(a.id, owed, amount in (owed, remaining.get(a.id)), a.id in recorded),
            )
        )
    return tuple(c for _, c in sorted(choices, key=lambda x: (not x[1].suggested, x[0])))
