"""Payments that come back month after month: rent, subscriptions, EMIs, a regular transfer.

A payee that shows up in at least three of the months looked at is reported with its usual
monthly amount. This does not know it is a subscription; it only knows it recurs.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from cfo.core.dates import month_bounds, month_key
from cfo.core.types import Account, Transaction
from cfo.metrics.flows import Bucket, flows
from cfo.metrics.trend import mean


@dataclass(frozen=True, slots=True)
class RecurringPayment:
    payee: str
    category: str | None
    months_seen: int
    average_monthly: int
    latest_amount: int  # the payee's total in the latest month it appeared
    last_date: date
    steady: bool  # every month within a tenth of the average


def recurring_payments(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    months: Sequence[str],
    min_months: int = 3,
) -> tuple[RecurringPayment, ...]:
    if not months:
        return ()
    start, end = month_bounds(months[0])[0], month_bounds(months[-1])[1]
    allowed = set(months)
    per_month: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    last: dict[str, date] = {}
    names: dict[str, str] = {}
    category: dict[str, str | None] = {}
    for f in flows(accounts, transactions, start, end):
        if not f.out or f.bucket is not Bucket.SPENDING or month_key(f.date) not in allowed:
            continue
        key = f.payee.strip().casefold()
        if not key:
            continue
        per_month[key][month_key(f.date)] += abs(f.amount)
        names.setdefault(key, f.payee.strip())
        if key not in last or f.date >= last[key]:
            last[key] = f.date
            category[key] = f.counterpart.display_name if f.counterpart else None
    found: list[RecurringPayment] = []
    for key, by_month in per_month.items():
        if len(by_month) < min_months:
            continue
        totals = [by_month[m] for m in sorted(by_month)]
        avg = mean(totals)
        found.append(
            RecurringPayment(
                names[key],
                category[key],
                len(by_month),
                avg,
                totals[-1],
                last[key],
                (max(totals) - min(totals)) * 10 <= avg,
            )
        )
    return tuple(sorted(found, key=lambda r: (-r.average_monthly, r.payee)))
