from cfo.metrics.reconcile import gaps, opening_amount
from cfo.testing.books import ACCOUNTS, DINING, OPEN, SAV
from cfo.testing.helpers import INF, OBS, SYS, assertion, d, txn


def test_gap_reports_the_difference() -> None:
    txs = [txn("2026-09-01", (SAV, 21000000, OBS), (OPEN, -21000000, SYS))]
    (gap,) = gaps(ACCOUNTS, txs, [assertion(SAV, "2026-09-30", 23373200)])
    assert (gap.account_id, gap.as_of, gap.expected, gap.actual, gap.difference) == (
        SAV.id,
        d("2026-09-30"),
        23373200,
        21000000,
        2373200,
    )


def test_matching_assertion_is_no_gap() -> None:
    txs = [txn("2026-09-01", (SAV, 100, OBS), (OPEN, -100, SYS))]
    assert gaps(ACCOUNTS, txs, [assertion(SAV, "2026-09-30", 100)]) == ()


def test_opening_amount_makes_first_assertion_hold() -> None:
    txs = [txn("2026-09-03", (SAV, -64000, OBS), (DINING, 64000, INF))]
    first = assertion(SAV, "2026-09-30", 23373200)
    amount = opening_amount(SAV.id, txs, first)
    assert amount == 23373200 + 64000
    opened = [*txs, txn("2026-09-02", (SAV, amount, SYS), (OPEN, -amount, SYS))]
    assert gaps(ACCOUNTS, opened, [first]) == ()
