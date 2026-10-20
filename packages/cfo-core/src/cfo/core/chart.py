"""The default chart of accounts: system accounts every ledger has, the default categories it
starts with, and how a real account's path is built."""

from __future__ import annotations

import re
from dataclasses import dataclass

from cfo.core.types import AccountKind, AccountType, Direction, Heading

OPENING = "Equity:Opening"
REVALUATION = "Equity:Revaluation"
IN_TRANSIT = "Assets:InTransit"  # left one of the owner's accounts for another not yet seen
UNCATEGORIZED_OUT = "Expenses:Uncategorized"
UNCATEGORIZED_IN = "Income:Uncategorized"

SYSTEM_ACCOUNTS: tuple[tuple[str, AccountKind], ...] = (
    (OPENING, AccountKind.EQUITY),
    (REVALUATION, AccountKind.EQUITY),
    (IN_TRANSIT, AccountKind.ASSET),
    (UNCATEGORIZED_OUT, AccountKind.EXPENSE),
    (UNCATEGORIZED_IN, AccountKind.INCOME),
)

SYSTEM_NAMES = {
    OPENING: "Opening balances",
    REVALUATION: "Revaluation",
    IN_TRANSIT: "Money in transit",
    UNCATEGORIZED_OUT: "Uncategorized",
    UNCATEGORIZED_IN: "Uncategorized",
}


@dataclass(frozen=True, slots=True)
class CategoryDef:
    path: str
    name: str
    description: str
    direction: Direction
    heading: Heading = Heading.REGULAR


_IN, _OUT = Direction.IN, Direction.OUT

DEFAULT_CATEGORIES: tuple[CategoryDef, ...] = (
    CategoryDef("Income:Salary", "Salary", "Pay from your employer", _IN),
    CategoryDef("Income:Other", "Other income", "Money in that is not salary or interest", _IN),
    CategoryDef("Income:Interest", "Interest", "Interest and dividends", _IN),
    CategoryDef("Income:Rewards", "Rewards", "Cashback and card rewards", _IN, Heading.REWARDS),
    CategoryDef(
        "Income:People:Received",
        "Received from people",
        "Money friends and family send you",
        _IN,
        Heading.PEOPLE,
    ),
    CategoryDef("Expenses:Housing", "Housing", "Rent, maintenance, home loan interest", _OUT),
    CategoryDef(
        "Expenses:Utilities", "Utilities", "Electricity, water, gas, internet, phone", _OUT
    ),
    CategoryDef(
        "Expenses:Subscriptions",
        "Subscriptions",
        "Streaming, apps and other recurring services",
        _OUT,
    ),
    CategoryDef("Expenses:Food:Dining", "Dining", "Restaurants, cafés, food delivery", _OUT),
    CategoryDef("Expenses:Food:Groceries", "Groceries", "Supermarkets and daily provisions", _OUT),
    CategoryDef("Expenses:Shopping", "Shopping", "Clothes, electronics, online shopping", _OUT),
    CategoryDef("Expenses:Health", "Health", "Doctors, medicines, insurance", _OUT),
    CategoryDef("Expenses:Transport", "Transport", "Fuel, cabs, public transport", _OUT),
    CategoryDef("Expenses:Travel", "Travel", "Flights, hotels, holidays", _OUT),
    CategoryDef("Expenses:Fees", "Fees", "Bank charges, card fees, interest paid", _OUT),
    CategoryDef(
        "Expenses:People:Sent",
        "Sent to people",
        "Money you send to friends and family",
        _OUT,
        Heading.PEOPLE,
    ),
)

_UNSAFE = re.compile(r"[^A-Za-z0-9]+")


def slug(text: str) -> str:
    """One path segment: letters and digits, everything else collapsed to a single hyphen."""
    return _UNSAFE.sub("-", text.strip()).strip("-") or "Account"


def real_account_path(type: AccountType, institution: str, name: str) -> str:
    return f"{type.path_root}:{slug(institution)}:{slug(name)}"
