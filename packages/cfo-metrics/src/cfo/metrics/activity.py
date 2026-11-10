"""Per-account activity over a period: what each account spent, received and moved.

Answers "which credit card had the most spending", "which bank account made the most payments",
"how much came into my savings". Computed in integer paise here, and ranked here, so a model
only reads the answer.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from cfo.core.ids import Id
from cfo.core.types import Account, Transaction
from cfo.metrics.flows import Bucket, flows


@dataclass(frozen=True, slots=True)
class AccountActivity:
    account_id: Id
    spending: int  # purchases and bills: outflow to expense categories
    people_out: int  # sent to friends and family
    transfers_out: int  # moved to the owner's own accounts, such as a card bill payment
    other_out: int
    income: int
    people_in: int
    transfers_in: int
    refunds: int  # money back from an expense category
    other_in: int
    transactions: int  # every movement in the period
    payments: int  # movements out of the account

    @property
    def total_out(self) -> int:
        return self.spending + self.people_out + self.transfers_out + self.other_out

    @property
    def total_in(self) -> int:
        return self.income + self.people_in + self.transfers_in + self.refunds + self.other_in


def account_activity(
    accounts: Sequence[Account], transactions: Sequence[Transaction], start: date, end: date
) -> tuple[AccountActivity, ...]:
    """One line for each real account that had any movement, in account-id order."""
    sums: dict[Id, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for f in flows(accounts, transactions, start, end):
        if f.bucket is Bucket.OTHER:  # opening balances and revaluation are not payments
            continue
        s = sums[f.account_id]
        s["transactions"] += 1
        size = abs(f.amount)
        if f.out:
            s["payments"] += 1
            key = {
                Bucket.SPENDING: "spending",
                Bucket.PEOPLE: "people_out",
                Bucket.TRANSFER: "transfers_out",
            }.get(f.bucket, "other_out")
        else:
            key = {
                Bucket.INCOME: "income",
                Bucket.PEOPLE: "people_in",
                Bucket.TRANSFER: "transfers_in",
                Bucket.SPENDING: "refunds",
            }.get(f.bucket, "other_in")
        s[key] += size
    return tuple(
        AccountActivity(
            account_id,
            *(
                s[k]
                for k in (
                    "spending",
                    "people_out",
                    "transfers_out",
                    "other_out",
                    "income",
                    "people_in",
                    "transfers_in",
                    "refunds",
                    "other_in",
                    "transactions",
                    "payments",
                )
            ),
        )
        for account_id, s in sorted(sums.items(), key=lambda kv: str(kv[0]))
    )


def ranks(values: dict[Id, int]) -> dict[Id, int]:
    """Competition ranking, biggest first (1, 1, 3 for a tie). Zero earns no rank."""
    ordered = sorted((v for v in values.values() if v > 0), reverse=True)
    return {k: ordered.index(v) + 1 for k, v in values.items() if v > 0}
