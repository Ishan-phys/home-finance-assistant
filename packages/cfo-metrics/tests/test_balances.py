from cfo.metrics.balances import balance, balances_at
from cfo.testing.books import DINING, OPEN, SAV
from cfo.testing.helpers import INF, OBS, SYS, d, txn


def test_balances_sum_postings_up_to_the_date() -> None:
    txs = [
        txn("2026-09-01", (SAV, 100000, OBS), (OPEN, -100000, SYS)),
        txn("2026-09-10", (SAV, -640, OBS), (DINING, 640, INF)),
    ]
    assert balances_at(txs, d("2026-09-05"))[SAV.id] == 100000
    assert balance(SAV.id, txs, d("2026-09-30")) == 99360
    assert balance(SAV.id, txs) == 99360
