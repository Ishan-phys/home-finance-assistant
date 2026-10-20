"""Where money came from and went over a period, and the check that ties it to net worth."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from cfo.core.chart import REVALUATION
from cfo.core.ids import Id
from cfo.core.types import Account, AccountKind, Heading, Transaction
from cfo.metrics.balance_sheet import BalanceSheet


@dataclass(frozen=True, slots=True)
class CategoryLine:
    path: str
    name: str
    amount: int  # natural sign, children included
    depth: int  # 1 for a top-level category such as Expenses:Food
    account_id: Id | None  # None for a grouping node that is not itself an account
    kind: AccountKind


@dataclass(frozen=True, slots=True)
class IncomeStatement:
    start: date
    end: date
    earned: int  # regular income, natural sign
    spent: int  # regular spending
    rewards: int
    people_in: int
    people_out: int
    revaluation: int  # gains posted to Equity:Revaluation
    opening: int  # opening balances first recorded inside the period
    categories: tuple[CategoryLine, ...]

    @property
    def saved(self) -> int:
        return self.earned + self.rewards + self.people_in - self.spent - self.people_out


@dataclass(frozen=True, slots=True)
class CheckLine:
    change_in_net_worth: int
    saved: int
    revaluation: int
    opening: int
    unrealized_change: int

    @property
    def explained(self) -> int:
        return self.saved + self.revaluation + self.opening + self.unrealized_change

    @property
    def ok(self) -> bool:
        return self.change_in_net_worth == self.explained


def income_statement(
    accounts: Sequence[Account], transactions: Sequence[Transaction], start: date, end: date
) -> IncomeStatement:
    by_id = {a.id: a for a in accounts}
    own: dict[Id, int] = defaultdict(int)  # natural-signed activity per income/expense account
    revaluation = opening = 0
    for t in transactions:
        if not start <= t.date <= end:
            continue
        for p in t.postings:
            a = by_id.get(p.account_id)
            if a is None:
                continue
            if a.kind is AccountKind.EXPENSE:
                own[a.id] += p.amount
            elif a.kind is AccountKind.INCOME:
                own[a.id] -= p.amount
            elif a.kind is AccountKind.EQUITY:
                if a.path == REVALUATION:
                    revaluation -= p.amount
                else:
                    opening -= p.amount
    bands: dict[tuple[AccountKind, Heading], int] = defaultdict(int)
    for account_id, amount in own.items():
        a = by_id[account_id]
        bands[(a.kind, a.heading)] += amount
    inc, exp = AccountKind.INCOME, AccountKind.EXPENSE
    return IncomeStatement(
        start=start,
        end=end,
        earned=bands[(inc, Heading.REGULAR)],
        spent=bands[(exp, Heading.REGULAR)] + bands[(exp, Heading.REWARDS)],
        rewards=bands[(inc, Heading.REWARDS)],
        people_in=bands[(inc, Heading.PEOPLE)],
        people_out=bands[(exp, Heading.PEOPLE)],
        revaluation=revaluation,
        opening=opening,
        categories=_tree(by_id, own),
    )


def _tree(by_id: dict[Id, Account], own: dict[Id, int]) -> tuple[CategoryLine, ...]:
    """Every account with activity, and every grouping path above it, with children rolled up."""
    by_path = {a.path: a for a in by_id.values()}
    totals: dict[str, int] = defaultdict(int)
    kinds: dict[str, AccountKind] = {}
    for account_id, amount in own.items():
        if amount == 0:
            continue
        a = by_id[account_id]
        parts = a.path.split(":")
        for i in range(2, len(parts) + 1):
            path = ":".join(parts[:i])
            totals[path] += amount
            kinds[path] = a.kind
    lines = []
    for path in sorted(totals):
        account = by_path.get(path)
        name = account.display_name if account else path.rsplit(":", 1)[-1]
        lines.append(
            CategoryLine(
                path,
                name,
                totals[path],
                path.count(":"),
                account.id if account else None,
                kinds[path],
            )
        )
    return tuple(lines)


def check_line(before: BalanceSheet, after: BalanceSheet, stmt: IncomeStatement) -> CheckLine:
    """Net worth from the day before the period to its end, against what the period explains.
    Valuations post nothing, so the change in unrealized gain is part of the explanation."""
    return CheckLine(
        change_in_net_worth=after.total - before.total,
        saved=stmt.saved,
        revaluation=stmt.revaluation,
        opening=stmt.opening,
        unrealized_change=after.unrealized - before.unrealized,
    )
