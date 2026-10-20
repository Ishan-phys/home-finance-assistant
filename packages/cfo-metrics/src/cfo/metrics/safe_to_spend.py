"""How much can be spent without touching the base amount or what is already owed on cards."""

from __future__ import annotations

from dataclasses import dataclass

from cfo.core.types import AccountType, Group
from cfo.metrics.balance_sheet import BalanceSheet


@dataclass(frozen=True, slots=True)
class SafeToSpend:
    liquid: int
    kept_aside: int
    owed_on_cards: int  # positive
    available: int
    allowance_remaining: int | None  # None when no monthly allowance is set
    amount: int


def safe_to_spend(
    sheet: BalanceSheet, min_cash_buffer: int, monthly_allowance: int | None, spent_this_month: int
) -> SafeToSpend:
    # Only the owner's own cash and savings accounts: money in transit is already on its way
    # to another account and cannot be spent twice.
    liquid = sum(line.balance for line in sheet.lines if line.group is Group.LIQUID and line.type)
    cards = -sum(line.balance for line in sheet.lines if line.type is AccountType.CREDIT_CARD)
    owed = max(0, cards)
    available = max(0, liquid - min_cash_buffer - owed)
    remaining = None if monthly_allowance is None else max(0, monthly_allowance - spent_this_month)
    amount = available if remaining is None else min(available, remaining)
    return SafeToSpend(liquid, min_cash_buffer, owed, available, remaining, amount)
