from cfo.core.chart import (
    DEFAULT_CATEGORIES,
    IN_TRANSIT,
    SYSTEM_ACCOUNTS,
    real_account_path,
    slug,
)
from cfo.core.types import AccountKind, AccountType, Direction, Heading


def test_default_categories_match_the_spec() -> None:
    paths = [c.path for c in DEFAULT_CATEGORIES]
    assert len(paths) == len(set(paths)) == 16
    assert "Expenses:Food:Dining" in paths and "Income:People:Received" in paths
    assert all(c.description for c in DEFAULT_CATEGORIES)
    people = {c.path for c in DEFAULT_CATEGORIES if c.heading is Heading.PEOPLE}
    assert people == {"Income:People:Received", "Expenses:People:Sent"}
    assert {c.path for c in DEFAULT_CATEGORIES if c.heading is Heading.REWARDS} == {
        "Income:Rewards"
    }
    for c in DEFAULT_CATEGORIES:
        assert c.path.startswith("Income:" if c.direction is Direction.IN else "Expenses:")


def test_system_accounts() -> None:
    assert dict(SYSTEM_ACCOUNTS)[IN_TRANSIT] is AccountKind.ASSET
    assert len(SYSTEM_ACCOUNTS) == 5


def test_real_account_path() -> None:
    assert (
        real_account_path(AccountType.SAVINGS, "HDFC", "HDFC Savings")
        == "Assets:Bank:HDFC:HDFC-Savings"
    )
    assert (
        real_account_path(AccountType.CREDIT_CARD, "HDFC", "Millennia")
        == "Liabilities:Cards:HDFC:Millennia"
    )
    assert slug("SBI FD") == "SBI-FD" and slug("  a/b:c  ") == "a-b-c"
