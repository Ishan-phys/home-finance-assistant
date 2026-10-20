from cfo.core.types import Group
from cfo.metrics.balance_sheet import balance_sheet
from cfo.testing.books import ACCOUNTS, CARD, DINING, FD, FUND, OPEN, SAV, TRANSIT
from cfo.testing.helpers import INF, OBS, SYS, d, txn, valuation


def test_net_worth_is_assets_plus_liabilities() -> None:
    txs = [
        txn("2026-09-01", (SAV, 23373200, OBS), (OPEN, -23373200, SYS)),
        txn("2026-09-05", (CARD, -1626800, OBS), (DINING, 1626800, INF)),
    ]
    sheet = balance_sheet(ACCOUNTS, txs, [], d("2026-09-30"))
    assert sheet.total == 23373200 - 1626800
    assert sheet.groups[Group.OWED] == -1626800
    assert sheet.groups[Group.LIQUID] == 23373200
    # every active real account is listed, even at zero; system accounts only when non-zero
    assert {line.account_id for line in sheet.lines} == {SAV.id, CARD.id, FUND.id, FD.id}


def test_holdings_use_latest_valuation_and_report_unrealized() -> None:
    txs = [txn("2026-09-02", (FUND, 1000000, OBS), (SAV, -1000000, OBS))]
    vals = [valuation(FUND, "2026-09-15", 1050000), valuation(FUND, "2026-09-30", 1100000)]
    sheet = balance_sheet(ACCOUNTS, txs, vals, d("2026-09-30"))
    line = next(x for x in sheet.lines if x.account_id == FUND.id)
    assert (line.cost, line.market, line.balance, line.unrealized) == (
        1000000,
        1100000,
        1100000,
        100000,
    )
    assert balance_sheet(ACCOUNTS, txs, vals, d("2026-09-20")).groups[Group.INVESTMENTS] == 1050000


def test_money_in_transit_counts_as_liquid() -> None:
    txs = [
        txn("2026-09-01", (SAV, 50000, OBS), (OPEN, -50000, SYS)),
        txn("2026-09-04", (SAV, -16268, OBS), (TRANSIT, 16268, INF)),
    ]
    sheet = balance_sheet(ACCOUNTS, txs, [], d("2026-09-30"))
    assert sheet.total == 50000 and sheet.groups[Group.LIQUID] == 50000
