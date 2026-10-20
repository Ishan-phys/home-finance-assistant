"""Balance assertions from statements, against what the ledger computes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from cfo.core.ids import Id
from cfo.core.types import Account, Assertion, Transaction
from cfo.metrics.balances import balance


@dataclass(frozen=True, slots=True)
class Gap:
    account_id: Id
    as_of: date
    expected: int  # what the statement says
    actual: int  # what the ledger computes
    difference: int  # expected - actual: positive means the ledger is short


def gaps(
    accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    assertions: Sequence[Assertion],
) -> tuple[Gap, ...]:
    live = {a.id for a in accounts}
    out = []
    for a in sorted(assertions, key=lambda x: (x.as_of, str(x.account_id))):
        if a.account_id not in live:
            continue
        actual = balance(a.account_id, transactions, a.as_of)
        if actual != a.amount:
            out.append(Gap(a.account_id, a.as_of, a.amount, actual, a.amount - actual))
    return tuple(out)


def opening_amount(account_id: Id, transactions: Sequence[Transaction], earliest: Assertion) -> int:
    """The opening balance that makes the earliest assertion hold, given every other posting."""
    return earliest.amount - balance(account_id, transactions, earliest.as_of)
