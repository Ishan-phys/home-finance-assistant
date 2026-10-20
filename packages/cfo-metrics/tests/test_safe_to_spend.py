from cfo.metrics.balance_sheet import balance_sheet
from cfo.metrics.safe_to_spend import safe_to_spend
from cfo.testing.books import ACCOUNTS, CARD, DINING, OPEN, SAV
from cfo.testing.helpers import INF, OBS, SYS, d, txn

TXS = [
    txn("2026-09-01", (SAV, 20000000, OBS), (OPEN, -20000000, SYS)),
    txn("2026-09-05", (CARD, -1626800, OBS), (DINING, 1626800, INF)),
]
SHEET = balance_sheet(ACCOUNTS, TXS, [], d("2026-09-30"))


def test_subtracts_base_amount_and_card_balance() -> None:
    s = safe_to_spend(SHEET, min_cash_buffer=5000000, monthly_allowance=None, spent_this_month=0)
    assert (s.liquid, s.kept_aside, s.owed_on_cards) == (20000000, 5000000, 1626800)
    assert s.available == s.amount == 20000000 - 5000000 - 1626800
    assert s.allowance_remaining is None


def test_capped_by_the_months_allowance() -> None:
    s = safe_to_spend(SHEET, min_cash_buffer=0, monthly_allowance=3000000, spent_this_month=1626800)
    assert s.allowance_remaining == 3000000 - 1626800 and s.amount == s.allowance_remaining


def test_never_negative() -> None:
    s = safe_to_spend(SHEET, min_cash_buffer=99999999, monthly_allowance=100, spent_this_month=500)
    assert s.available == 0 and s.allowance_remaining == 0 and s.amount == 0


def test_money_in_transit_is_not_spendable() -> None:
    from cfo.testing.books import TRANSIT

    txs = [*TXS, txn("2026-09-04", (SAV, -1000000, OBS), (TRANSIT, 1000000, INF))]
    sheet = balance_sheet(ACCOUNTS, txs, [], d("2026-09-30"))
    s = safe_to_spend(sheet, min_cash_buffer=0, monthly_allowance=None, spent_this_month=0)
    assert s.liquid == 20000000 - 1000000
