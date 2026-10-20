"""A small chart of accounts shared by the metric and ledger tests."""

from cfo.core.chart import IN_TRANSIT, OPENING, REVALUATION, UNCATEGORIZED_IN, UNCATEGORIZED_OUT
from cfo.core.types import AccountType, Direction, Heading
from cfo.testing.helpers import category, real, system

SAV = real(AccountType.SAVINGS, "HDFC Savings", id=1)
CARD = real(AccountType.CREDIT_CARD, "HDFC Card", id=2)
FUND = real(AccountType.MUTUAL_FUND, "Groww MF", institution="Groww", id=3)
FD = real(AccountType.FIXED_DEPOSIT, "SBI FD", institution="SBI", id=4)
DINING = category("Expenses:Food:Dining")
GROCERIES = category("Expenses:Food:Groceries")
RENT = category("Expenses:Housing")
SALARY = category("Income:Salary", Direction.IN)
REWARDS = category("Income:Rewards", Direction.IN, Heading.REWARDS)
FROM_PEOPLE = category("Income:People:Received", Direction.IN, Heading.PEOPLE)
TO_PEOPLE = category("Expenses:People:Sent", Direction.OUT, Heading.PEOPLE)
OPEN, REVAL, TRANSIT = system(OPENING), system(REVALUATION), system(IN_TRANSIT)
UNCAT_OUT, UNCAT_IN = system(UNCATEGORIZED_OUT), system(UNCATEGORIZED_IN)
ACCOUNTS = [
    SAV,
    CARD,
    FUND,
    FD,
    DINING,
    GROCERIES,
    RENT,
    SALARY,
    REWARDS,
    FROM_PEOPLE,
    TO_PEOPLE,
    OPEN,
    REVAL,
    TRANSIT,
    UNCAT_OUT,
    UNCAT_IN,
]
