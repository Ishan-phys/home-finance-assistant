import pytest
from cfo.metrics.trend import category_moves, mean, monthly_trend, percent
from cfo.testing.books import ACCOUNTS, DINING, RENT, SALARY, SAV
from cfo.testing.helpers import INF, OBS, txn


def test_percent_rounds_half_away_from_zero_and_refuses_a_missing_base() -> None:
    assert percent(1, 3) == 33
    assert percent(1, 8) == 13  # 12.5 rounds up
    assert percent(-1, 8) == -13
    assert percent(5, 0) is None and percent(5, -100) is None
    assert percent(0, 100) == 0


def test_mean_rounds_half_up() -> None:
    assert mean([1, 2]) == 2  # 1.5
    assert mean([-3, 0]) == -1  # -1.5 rounds up toward zero
    with pytest.raises(ValueError):
        mean([])


def books():  # type: ignore[no-untyped-def]
    return [
        txn("2026-08-01", (SAV, 100_00, OBS), (SALARY, -100_00, INF)),
        txn("2026-08-05", (SAV, -20_00, OBS), (DINING, 20_00, INF)),
        txn("2026-08-06", (SAV, -30_00, OBS), (RENT, 30_00, INF)),
        txn("2026-09-01", (SAV, 100_00, OBS), (SALARY, -100_00, INF)),
        txn("2026-09-05", (SAV, -45_00, OBS), (DINING, 45_00, INF)),
        txn("2026-09-06", (SAV, -30_00, OBS), (RENT, 30_00, INF)),
    ]


def test_monthly_trend_compares_each_month_with_the_one_before() -> None:
    aug, sep = monthly_trend(ACCOUNTS, books(), ["2026-08", "2026-09"])
    assert (aug.net_in, aug.net_out, aug.saved, aug.savings_rate) == (100_00, 50_00, 50_00, 50)
    assert (aug.net_out_change, aug.net_out_change_pct) == (None, None)
    assert (sep.net_out, sep.saved, sep.savings_rate) == (75_00, 25_00, 25)
    assert (sep.net_out_change, sep.net_out_change_pct) == (25_00, 50)


def test_category_moves_show_share_and_change_against_last_month() -> None:
    moves = category_moves(ACCOUNTS, books(), "2026-09")
    food, housing = moves  # Dining rolls up into Food, the top-level category
    assert (food.name, food.amount, food.share, food.previous_amount) == ("Food", 45_00, 60, 20_00)
    assert (food.change, food.change_pct) == (25_00, 125)
    assert (housing.name, housing.change, housing.change_pct, housing.share) == (
        "Housing",
        0,
        0,
        40,
    )
