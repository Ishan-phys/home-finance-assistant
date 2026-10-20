"""What the owner owns and owes on a date. Net worth is assets plus liabilities (liabilities are
negative). Holdings show their latest market value when one is known; the difference from cost is
unrealized gain, which is reported, never posted."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from cfo.core.ids import Id
from cfo.core.types import Account, AccountKind, AccountType, Group, Transaction, Valuation
from cfo.metrics.balances import balances_at


@dataclass(frozen=True, slots=True)
class SheetLine:
    account_id: Id
    group: Group
    type: AccountType | None
    balance: int  # what counts toward net worth: market value for valued holdings, else cost
    cost: int  # the sum of postings
    market: int | None  # latest valuation on or before the date, holdings only
    unrealized: int  # market - cost, or 0


@dataclass(frozen=True, slots=True)
class BalanceSheet:
    as_of: date
    total: int
    groups: dict[Group, int]
    lines: tuple[SheetLine, ...]

    @property
    def unrealized(self) -> int:
        return sum(line.unrealized for line in self.lines)


def _latest(valuations: Sequence[Valuation], as_of: date) -> dict[Id, int]:
    best: dict[Id, tuple[date, int, int]] = {}
    for i, v in enumerate(valuations):
        if v.as_of <= as_of and (
            v.account_id not in best or (v.as_of, i) >= best[v.account_id][:2]
        ):
            best[v.account_id] = (v.as_of, i, v.amount)
    return {k: amount for k, (_, _, amount) in best.items()}


def balance_sheet(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    valuations: Sequence[Valuation],
    as_of: date,
) -> BalanceSheet:
    costs = balances_at(transactions, as_of)
    markets = _latest(valuations, as_of)
    lines: list[SheetLine] = []
    for a in accounts:
        if a.kind not in (AccountKind.ASSET, AccountKind.LIABILITY):
            continue
        # Money in transit between the owner's own accounts is still theirs, and liquid.
        group = a.group or Group.LIQUID
        cost = costs.get(a.id, 0)
        market = markets.get(a.id) if group is Group.INVESTMENTS else None
        if cost == 0 and market is None and (a.type is None or not a.active):
            continue
        value = cost if market is None else market
        lines.append(
            SheetLine(
                a.id, group, a.type, value, cost, market, 0 if market is None else market - cost
            )
        )
    groups = {g: sum(line.balance for line in lines if line.group is g) for g in Group}
    return BalanceSheet(as_of, sum(groups.values()), groups, tuple(lines))
