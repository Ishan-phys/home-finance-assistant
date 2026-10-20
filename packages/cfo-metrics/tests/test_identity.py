"""Whatever the ledger, the change in net worth is explained by the income statement."""

from datetime import date, timedelta

from cfo.metrics.balance_sheet import balance_sheet
from cfo.metrics.income_statement import check_line, income_statement
from cfo.testing.books import (
    ACCOUNTS,
    CARD,
    DINING,
    FD,
    FROM_PEOPLE,
    FUND,
    OPEN,
    REVAL,
    REWARDS,
    SALARY,
    SAV,
    TO_PEOPLE,
    TRANSIT,
)
from cfo.testing.helpers import INF, OBS, SYS, txn, valuation
from hypothesis import given, settings
from hypothesis import strategies as st

PAIRS = [
    (SAV, SALARY),
    (SAV, DINING),
    (CARD, DINING),
    (CARD, REWARDS),
    (SAV, FROM_PEOPLE),
    (SAV, TO_PEOPLE),
    (SAV, FUND),
    (SAV, CARD),
    (SAV, TRANSIT),
    (FD, REVAL),
    (FD, OPEN),
    (SAV, OPEN),
]
BASE = date(2026, 8, 1)


@st.composite
def ledgers(draw):  # type: ignore[no-untyped-def]
    txs = []
    for _ in range(draw(st.integers(0, 25))):
        a, b = draw(st.sampled_from(PAIRS))
        amount = draw(st.integers(-(10**7), 10**7).filter(bool))
        day = BASE + timedelta(days=draw(st.integers(0, 90)))
        origin = SYS if b in (OPEN, REVAL) else INF
        txs.append(txn(day.isoformat(), (a, amount, OBS), (b, -amount, origin)))
    vals = [
        valuation(
            FUND,
            (BASE + timedelta(days=draw(st.integers(0, 90)))).isoformat(),
            draw(st.integers(0, 10**7)),
        )
        for _ in range(draw(st.integers(0, 3)))
    ]
    return txs, vals


@settings(max_examples=200, deadline=None)
@given(ledgers(), st.integers(0, 60), st.integers(0, 60))
def test_change_in_net_worth_is_explained(ledger, offset, length) -> None:  # type: ignore[no-untyped-def]
    txs, vals = ledger
    start = BASE + timedelta(days=offset)
    end = start + timedelta(days=length)
    before = balance_sheet(ACCOUNTS, txs, vals, start - timedelta(days=1))
    after = balance_sheet(ACCOUNTS, txs, vals, end)
    assert check_line(before, after, income_statement(ACCOUNTS, txs, start, end)).ok
