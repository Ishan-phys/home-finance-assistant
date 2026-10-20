from cfo.metrics.inbox import inbox
from cfo.testing.books import ACCOUNTS, CARD, OPEN, SAV, TRANSIT, UNCAT_OUT
from cfo.testing.helpers import INF, OBS, SYS, assertion, d, imp, txn


def test_inbox_lists_uncategorized_unpaired_gap_and_card_due() -> None:
    unknown = txn("2026-09-07", (SAV, -120000, OBS), (UNCAT_OUT, 120000, INF))
    billpay = txn("2026-09-04", (SAV, -1626800, OBS), (TRANSIT, 1626800, INF))
    txs = [txn("2026-09-01", (SAV, 100, OBS), (OPEN, -100, SYS)), unknown, billpay]
    card_import = imp(CARD, "2026-09-20", amount_due=500000, due_date=d("2026-10-05"))
    items = inbox(ACCOUNTS, txs, [assertion(SAV, "2026-09-30", 999)], [card_import])
    kinds = {(i.kind, i.amount) for i in items}
    assert ("uncategorized", 120000) in kinds and ("unpaired", 1626800) in kinds
    assert ("gap", abs(999 - (100 - 120000 - 1626800))) in kinds
    assert ("card_due", 500000) in kinds
    assert next(i for i in items if i.kind == "uncategorized").account_id == SAV.id
    assert [i.date for i in items] == sorted((i.date for i in items), reverse=True)


def test_card_due_clears_once_a_payment_lands_after_the_statement() -> None:
    card_import = imp(CARD, "2026-09-20", amount_due=500000, due_date=d("2026-10-05"))
    paid = txn("2026-09-28", (SAV, -500000, OBS), (CARD, 500000, OBS))
    assert [i.kind for i in inbox(ACCOUNTS, [paid], [], [card_import])] == []


def test_a_cashback_credit_is_not_a_card_payment() -> None:
    from cfo.testing.books import REWARDS

    card_import = imp(CARD, "2026-09-08", amount_due=390000, due_date=d("2026-10-03"))
    cashback = txn("2026-09-08", (CARD, 10000, OBS), (REWARDS, -10000, INF))
    assert [i.kind for i in inbox(ACCOUNTS, [cashback], [], [card_import])] == ["card_due"]
