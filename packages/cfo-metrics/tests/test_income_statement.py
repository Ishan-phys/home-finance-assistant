from cfo.metrics.balance_sheet import balance_sheet
from cfo.metrics.income_statement import check_line, income_statement
from cfo.testing.books import (
    ACCOUNTS,
    CARD,
    DINING,
    FD,
    FROM_PEOPLE,
    FUND,
    GROCERIES,
    OPEN,
    REVAL,
    REWARDS,
    SALARY,
    SAV,
    TO_PEOPLE,
)
from cfo.testing.helpers import INF, OBS, SYS, d, txn, valuation

START, END = d("2026-09-01"), d("2026-09-30")


def stmt(txs):  # type: ignore[no-untyped-def]
    return income_statement(ACCOUNTS, txs, START, END)


def test_card_payment_does_not_touch_income_statement() -> None:
    s = stmt([txn("2026-09-04", (SAV, -1626800, OBS), (CARD, 1626800, OBS))])
    assert (s.earned, s.spent, s.saved) == (0, 0, 0)


def test_earned_spent_saved() -> None:
    s = stmt(
        [
            txn("2026-09-01", (SAV, 15000000, OBS), (SALARY, -15000000, INF)),
            txn("2026-09-03", (SAV, -64000, OBS), (DINING, 64000, INF)),
            txn("2026-08-30", (SAV, -99999, OBS), (DINING, 99999, INF)),  # outside the month
        ]
    )
    assert (s.earned, s.spent, s.saved) == (15000000, 64000, 15000000 - 64000)


def test_people_and_rewards_are_separate_bands() -> None:
    s = stmt(
        [
            txn("2026-09-02", (SAV, -200000, OBS), (TO_PEOPLE, 200000, INF)),
            txn("2026-09-03", (SAV, 50000, OBS), (FROM_PEOPLE, -50000, INF)),
            txn("2026-09-04", (CARD, 10000, OBS), (REWARDS, -10000, INF)),
        ]
    )
    assert (s.earned, s.spent) == (0, 0)
    assert (s.people_out, s.people_in, s.rewards) == (200000, 50000, 10000)
    assert s.saved == 50000 + 10000 - 200000


def test_categories_roll_up_by_path() -> None:
    s = stmt(
        [
            txn("2026-09-03", (SAV, -64000, OBS), (DINING, 64000, INF)),
            txn("2026-09-04", (SAV, -30000, OBS), (GROCERIES, 30000, INF)),
        ]
    )
    by_path = {c.path: c.amount for c in s.categories}
    assert by_path["Expenses:Food"] == 94000
    assert by_path["Expenses:Food:Dining"] == 64000
    assert next(c for c in s.categories if c.path == "Expenses:Food").account_id is None


def test_check_line_explains_net_worth_change() -> None:
    txs = [
        txn("2026-08-31", (SAV, 1000000, OBS), (OPEN, -1000000, SYS)),
        txn("2026-09-01", (FD, 500000, OBS), (OPEN, -500000, SYS)),  # opening inside the period
        txn("2026-09-02", (SAV, 15000000, OBS), (SALARY, -15000000, INF)),
        txn("2026-09-05", (FUND, 200000, OBS), (SAV, -200000, OBS)),
        txn("2026-09-20", (FD, 10000, OBS), (REVAL, -10000, SYS)),
    ]
    vals = [valuation(FUND, "2026-09-30", 230000)]
    before = balance_sheet(ACCOUNTS, txs, vals, d("2026-08-31"))
    after = balance_sheet(ACCOUNTS, txs, vals, END)
    line = check_line(before, after, stmt(txs))
    assert line.ok
    assert line.change_in_net_worth == 15000000 + 500000 + 10000 + 30000
    assert (line.revaluation, line.opening, line.unrealized_change) == (10000, 500000, 30000)
