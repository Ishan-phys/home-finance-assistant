from datetime import date

import pytest
from cfo.core.errors import UnbalancedTransaction
from cfo.core.ids import new_id
from cfo.core.types import AccountKind, AccountType, Group, Origin, Posting, Transaction

DAY = date(2026, 9, 1)


def test_transaction_must_balance() -> None:
    a, b = new_id(), new_id()
    Transaction(
        new_id(),
        DAY,
        "x",
        "x",
        (Posting(a, -250, Origin.OBSERVED), Posting(b, 250, Origin.INFERRED)),
    )
    with pytest.raises(UnbalancedTransaction):
        Transaction(
            new_id(),
            DAY,
            "x",
            "x",
            (Posting(a, -250, Origin.OBSERVED), Posting(b, 200, Origin.INFERRED)),
        )
    with pytest.raises(UnbalancedTransaction):
        Transaction(new_id(), DAY, "x", "x", (Posting(a, 0, Origin.OBSERVED),))


def test_account_types_map_to_kind_group_and_root() -> None:
    assert (AccountType.CREDIT_CARD.kind, AccountType.CREDIT_CARD.group) == (
        AccountKind.LIABILITY,
        Group.OWED,
    )
    assert AccountType.FIXED_DEPOSIT.manual and not AccountType.SAVINGS.manual
    assert AccountType.MUTUAL_FUND.path_root == "Assets:Invest"
    assert AccountType.LOAN.path_root == "Liabilities:Loans"
    assert AccountType.CREDIT_CARD.label == "Credit card"
    assert all(t.label for t in AccountType)
