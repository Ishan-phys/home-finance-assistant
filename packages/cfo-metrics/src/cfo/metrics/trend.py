"""How things moved from month to month, and which categories moved them.

An explanation of finances is mostly comparison: this month against the last, against the usual,
one category against the whole. Those comparisons are arithmetic, so they are computed here, in
integer paise and whole percents, and a model only quotes them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cfo.core.dates import month_bounds, previous_month
from cfo.core.types import Account, AccountKind, Transaction
from cfo.metrics.income_statement import income_statement


def percent(part: int, whole: int) -> int | None:
    """`part` as a whole percent of `whole`, rounded half away from zero. None when `whole` is
    not positive, since a share of nothing (or of a debt) means nothing."""
    if whole <= 0:
        return None
    magnitude = (200 * abs(part) + whole) // (2 * whole)
    return magnitude if part >= 0 else -magnitude


def mean(values: Sequence[int]) -> int:
    """The average, rounded half up. Raises ValueError for no values."""
    if not values:
        raise ValueError("no values to average")
    return (2 * sum(values) + len(values)) // (2 * len(values))


@dataclass(frozen=True, slots=True)
class MonthTrend:
    month: str
    net_in: int
    net_out: int
    saved: int
    savings_rate: int | None  # saved as a whole percent of net_in
    net_out_change: int | None  # against the month before in the list; None for the first
    net_out_change_pct: int | None


def monthly_trend(
    accounts: Sequence[Account], transactions: Sequence[Transaction], months: Sequence[str]
) -> tuple[MonthTrend, ...]:
    """One line per month, in the order given (oldest first)."""
    lines: list[MonthTrend] = []
    for month in months:
        start, end = month_bounds(month)
        s = income_statement(accounts, transactions, start, end)
        before = lines[-1] if lines else None
        change = None if before is None else s.net_out - before.net_out
        lines.append(
            MonthTrend(
                month,
                s.net_in,
                s.net_out,
                s.saved,
                percent(s.saved, s.net_in),
                change,
                None if before is None or change is None else percent(change, before.net_out),
            )
        )
    return tuple(lines)


@dataclass(frozen=True, slots=True)
class CategoryMove:
    name: str
    amount: int
    share: int | None  # whole percent of the month's spending in categories
    previous_amount: int
    change: int
    change_pct: int | None  # None when the category had no spending the month before


def category_moves(
    accounts: Sequence[Account], transactions: Sequence[Transaction], month: str
) -> tuple[CategoryMove, ...]:
    """Top-level spending categories for `month`, biggest first, each against the month before.
    A category with spending only in the earlier month is listed too, with an amount of zero."""

    def totals(m: str) -> dict[str, int]:
        start, end = month_bounds(m)
        stmt = income_statement(accounts, transactions, start, end)
        return {
            c.name: c.amount
            for c in stmt.categories
            if c.kind is AccountKind.EXPENSE and c.depth == 1
        }

    now, before = totals(month), totals(previous_month(month))
    whole = sum(now.values())
    moves = [
        CategoryMove(
            name,
            now.get(name, 0),
            percent(now.get(name, 0), whole),
            before.get(name, 0),
            now.get(name, 0) - before.get(name, 0),
            percent(now.get(name, 0) - before.get(name, 0), before.get(name, 0)),
        )
        for name in sorted(set(now) | set(before))
    ]
    return tuple(sorted(moves, key=lambda m: (-m.amount, -m.previous_amount, m.name)))
