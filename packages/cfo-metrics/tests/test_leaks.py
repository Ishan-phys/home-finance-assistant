from cfo.metrics.leaks import NO_BASELINE, PARTIAL_MONTH, leaks
from cfo.testing.books import ACCOUNTS, DINING, SAV
from cfo.testing.helpers import INF, OBS, txn


def spend(day: str, amount: int, payee: str = "Swiggy"):  # type: ignore[no-untyped-def]
    return txn(day, (SAV, -amount, OBS), (DINING, amount, INF), payee=payee)


def test_variance_against_baseline_average() -> None:
    txs = [
        spend("2026-06-10", 1000),
        spend("2026-07-10", 2000),
        spend("2026-08-10", 3000),
        spend("2026-09-10", 5000),
        spend("2026-09-12", 1000),
    ]
    r = leaks(ACCOUNTS, txs, "2026-09", complete=True)
    assert r.baseline_months == ("2026-08", "2026-07", "2026-06")
    (row,) = r.variance or ()
    assert (row.payee, row.current, row.baseline_avg, row.variance, row.count) == (
        "Swiggy",
        6000,
        2000,
        4000,
        2,
    )


def test_reasons_when_no_variance() -> None:
    assert (
        leaks(ACCOUNTS, [spend("2026-09-10", 1)], "2026-09", complete=True).variance_reason
        == NO_BASELINE
    )
    assert (
        leaks(ACCOUNTS, [spend("2026-09-10", 1)], "2026-09", complete=False).variance_reason
        == PARTIAL_MONTH
    )


def test_an_opening_balance_month_is_not_a_baseline_month() -> None:
    from cfo.testing.books import OPEN
    from cfo.testing.helpers import SYS

    opening = txn("2026-08-31", (SAV, 100, SYS), (OPEN, -100, SYS), source="system")
    r = leaks(ACCOUNTS, [opening, spend("2026-09-10", 1)], "2026-09", complete=True)
    assert r.baseline_months == () and r.variance_reason == NO_BASELINE
