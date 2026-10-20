"""Spending that grew: this month's spend per payee against the average of earlier months."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from cfo.core.dates import month_bounds, month_key, previous_month
from cfo.core.ids import Id
from cfo.core.types import Account, AccountKind, Heading, Transaction

BASELINE_MONTHS = 3
PARTIAL_MONTH = "PARTIAL_MONTH"
NO_BASELINE = "NO_BASELINE"


@dataclass(frozen=True, slots=True)
class PayeeSpend:
    account_id: Id  # the category
    payee: str
    amount: int
    count: int


@dataclass(frozen=True, slots=True)
class LeakRow:
    account_id: Id
    payee: str
    current: int
    baseline_avg: int
    variance: int
    count: int


@dataclass(frozen=True, slots=True)
class LeakReport:
    month: str
    complete: bool
    current: tuple[PayeeSpend, ...]
    baseline_months: tuple[str, ...]
    variance: tuple[LeakRow, ...] | None
    variance_reason: str | None


def _round_half_up_div(total: int, n: int) -> int:
    return (2 * total + n) // (2 * n)


def _spend(accounts: Sequence[Account], txs: Sequence[Transaction], month: str) -> list[PayeeSpend]:
    expense = {
        a.id for a in accounts if a.kind is AccountKind.EXPENSE and a.heading is not Heading.PEOPLE
    }
    start, end = month_bounds(month)
    slots: dict[tuple[Id, str], list[int]] = defaultdict(lambda: [0, 0])
    for t in txs:
        if start <= t.date <= end:
            for p in t.postings:
                if p.account_id in expense:
                    slot = slots[(p.account_id, t.payee)]
                    slot[0] += p.amount
                    slot[1] += 1
    return sorted(
        (PayeeSpend(k[0], k[1], v[0], v[1]) for k, v in slots.items() if v[0]),
        key=lambda s: (-s.amount, str(s.account_id), s.payee),
    )


def leaks(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    month: str,
    *,
    complete: bool,
    baseline_months: int = BASELINE_MONTHS,
) -> LeakReport:
    current = _spend(accounts, transactions, month)
    data_months = {month_key(t.date) for t in transactions if t.source != "system"}
    baseline: list[str] = []
    cursor = previous_month(month)
    earliest = min(data_months) if data_months else cursor
    while len(baseline) < baseline_months and cursor >= earliest:
        if cursor in data_months:
            baseline.append(cursor)
        cursor = previous_month(cursor)
    by_month = {m: _spend(accounts, transactions, m) for m in baseline}

    variance: tuple[LeakRow, ...] | None = None
    reason: str | None = None
    if not complete:
        reason = PARTIAL_MONTH
    elif not baseline:
        reason = NO_BASELINE
    else:
        keys = {(s.account_id, s.payee) for s in current}
        for spends in by_month.values():
            keys |= {(s.account_id, s.payee) for s in spends}
        cur = {(s.account_id, s.payee): s for s in current}
        rows = []
        for key in keys:
            total = sum(
                s.amount
                for spends in by_month.values()
                for s in spends
                if (s.account_id, s.payee) == key
            )
            avg = _round_half_up_div(total, len(baseline))
            now = cur[key].amount if key in cur else 0
            rows.append(
                LeakRow(key[0], key[1], now, avg, now - avg, cur[key].count if key in cur else 0)
            )
        rows.sort(key=lambda r: (-r.variance, str(r.account_id), r.payee))
        variance = tuple(rows)
    return LeakReport(month, complete, tuple(current), tuple(baseline), variance, reason)
