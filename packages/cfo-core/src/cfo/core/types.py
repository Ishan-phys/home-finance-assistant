"""Plain, immutable domain records for a double-entry ledger. No I/O. Every amount is integer
paise, signed the Beancount way: assets and expenses grow positive; liabilities, income and
equity grow negative. A transaction's postings always sum to zero."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from cfo.core.errors import UnbalancedTransaction
from cfo.core.ids import Id


class AccountKind(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"
    EQUITY = "equity"


class AccountRole(StrEnum):
    REAL = "real"  # an account the owner holds: bank, card, loan, deposit, fund, property
    CATEGORY = "category"  # an Income or Expenses bucket
    SYSTEM = "system"  # opening balances, revaluation, money in transit, uncategorized


class Group(StrEnum):
    """Where a real account sits on the balance sheet."""

    LIQUID = "liquid"
    FIXED = "fixed"
    INVESTMENTS = "investments"
    OTHER = "other"
    OWED = "owed"


class AccountType(StrEnum):
    """What the owner picks in setup."""

    SAVINGS = "savings"
    CURRENT = "current"
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    LOAN = "loan"
    FIXED_DEPOSIT = "fixed_deposit"
    RECURRING_DEPOSIT = "recurring_deposit"
    MUTUAL_FUND = "mutual_fund"
    STOCK = "stock"
    PROPERTY = "property"
    GOLD = "gold"

    @property
    def kind(self) -> AccountKind:
        return _TYPES[self][0]

    @property
    def group(self) -> Group:
        return _TYPES[self][1]

    @property
    def path_root(self) -> str:
        return _TYPES[self][2]

    @property
    def manual(self) -> bool:
        """No statement feed: the owner gives a value and a date."""
        return _TYPES[self][3]

    @property
    def label(self) -> str:
        return _TYPES[self][4]


_A, _L = AccountKind.ASSET, AccountKind.LIABILITY
_TYPES: dict[AccountType, tuple[AccountKind, Group, str, bool, str]] = {
    AccountType.SAVINGS: (_A, Group.LIQUID, "Assets:Bank", False, "Savings account"),
    AccountType.CURRENT: (_A, Group.LIQUID, "Assets:Bank", False, "Current account"),
    AccountType.CASH: (_A, Group.LIQUID, "Assets:Cash", True, "Cash"),
    AccountType.CREDIT_CARD: (_L, Group.OWED, "Liabilities:Cards", False, "Credit card"),
    AccountType.LOAN: (_L, Group.OWED, "Liabilities:Loans", False, "Loan"),
    AccountType.FIXED_DEPOSIT: (_A, Group.FIXED, "Assets:Fixed", True, "Fixed deposit"),
    AccountType.RECURRING_DEPOSIT: (_A, Group.FIXED, "Assets:Fixed", True, "Recurring deposit"),
    AccountType.MUTUAL_FUND: (_A, Group.INVESTMENTS, "Assets:Invest", False, "Mutual funds"),
    AccountType.STOCK: (_A, Group.INVESTMENTS, "Assets:Invest", False, "Stocks"),
    AccountType.PROPERTY: (_A, Group.OTHER, "Assets:Other", True, "Property"),
    AccountType.GOLD: (_A, Group.OTHER, "Assets:Other", True, "Gold"),
}


class Origin(StrEnum):
    OBSERVED = "observed"  # read from a statement row or entered by hand: certain
    INFERRED = "inferred"  # our guess at the other side: a category, or money in transit
    OWNER = "owner"  # the other side as the owner set it
    SYSTEM = "system"  # opening balances and revaluations


class Direction(StrEnum):
    OUT = "out"
    IN = "in"


class Heading(StrEnum):
    """The income-statement band a category is reported under."""

    REGULAR = "regular"
    PEOPLE = "people"  # money to and from friends and family: neither earned nor lifestyle spend
    REWARDS = "rewards"  # cashback: shown apart from earned income


@dataclass(frozen=True, slots=True)
class Account:
    id: Id
    path: str
    kind: AccountKind
    role: AccountRole
    display_name: str
    type: AccountType | None = None  # real accounts only
    group: Group | None = None  # real accounts only
    description: str | None = None  # categories: what the category is for
    direction: Direction | None = None  # categories only
    heading: Heading = Heading.REGULAR
    institution: str | None = None
    binding: str | None = None  # the statement adapter; None for manual and non-real accounts
    cycle_day: int | None = None
    statement_fingerprint: str | None = None
    opened_on: date | None = None
    retired_on: date | None = None

    @property
    def active(self) -> bool:
        return self.retired_on is None


@dataclass(frozen=True, slots=True)
class Posting:
    account_id: Id
    amount: int
    origin: Origin
    id: Id | None = None
    import_id: Id | None = None
    dedup_hash: str | None = None  # observed postings from a statement only
    units: str | None = None  # holdings: an exact decimal, never multiplied into money
    unit_label: str | None = None


@dataclass(frozen=True, slots=True)
class Transaction:
    id: Id
    date: date
    narration: str  # redacted
    payee: str  # clean merchant
    postings: tuple[Posting, ...]
    source: Literal["import", "manual", "system"] = "import"
    import_id: Id | None = None

    def __post_init__(self) -> None:
        if len(self.postings) < 2 or sum(p.amount for p in self.postings) != 0:
            raise UnbalancedTransaction(
                f"transaction {self.id} has {len(self.postings)} postings summing to "
                f"{sum(p.amount for p in self.postings)}; it needs two or more summing to zero"
            )


@dataclass(frozen=True, slots=True)
class Assertion:
    """The statement says the account was `amount` (signed, as the ledger stores it) on `as_of`."""

    id: Id
    account_id: Id
    as_of: date
    amount: int
    import_id: Id | None = None


@dataclass(frozen=True, slots=True)
class Valuation:
    """Market value of a holding or manual asset on a date. Posts nothing."""

    id: Id
    account_id: Id
    as_of: date
    amount: int
    import_id: Id | None = None


@dataclass(frozen=True, slots=True)
class ImportRecord:
    id: Id
    account_id: Id
    period_end: date | None
    amount_due: int | None = None
    due_date: date | None = None
    closing_balance: int | None = None
    balance_as_of: date | None = None


class MappingSource(StrEnum):
    MODEL = "model"
    OWNER = "owner"


@dataclass(frozen=True, slots=True)
class MerchantMapping:
    lookup_key: str  # the raw description today; an HMAC of it from iteration 4
    clean_merchant: str
    label: str  # the account path the description is posted against
    source: MappingSource
    confidence: float | None = None  # the model's own confidence, when it gave one


@dataclass(frozen=True, slots=True)
class Person:
    id: Id
    name: str


@dataclass(frozen=True, slots=True)
class Ledger:
    """One person's complete financial record, and the unit of isolation (spec 3.10)."""

    id: Id
    person_id: Id


@dataclass(frozen=True, slots=True)
class Household:
    id: Id
    name: str


@dataclass(frozen=True, slots=True)
class Scope:
    """What a read covers: one ledger, or every member ledger of a household. Repositories refuse
    to run without one, and a write needs exactly one ledger."""

    ledger_ids: frozenset[Id]

    @classmethod
    def of(cls, *ledger_ids: Id) -> Scope:
        return cls(frozenset(ledger_ids))

    def single(self) -> Id:
        if len(self.ledger_ids) != 1:
            raise ValueError("a write needs a scope of exactly one ledger")
        return next(iter(self.ledger_ids))

    def __contains__(self, ledger_id: object) -> bool:
        return ledger_id in self.ledger_ids

    def __or__(self, other: Scope) -> Scope:
        return Scope(self.ledger_ids | other.ledger_ids)
