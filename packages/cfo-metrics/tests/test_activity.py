"""Which account spent, paid or received the most; finding movements; regular payments."""

from cfo.metrics.activity import account_activity, ranks
from cfo.metrics.flows import Bucket, flows
from cfo.metrics.recurring import recurring_payments
from cfo.metrics.search import by_month, find_flows, largest_first
from cfo.testing.books import (
    ACCOUNTS,
    CARD,
    DINING,
    FROM_PEOPLE,
    OPEN,
    RENT,
    SALARY,
    SAV,
    TO_PEOPLE,
    TRANSIT,
)
from cfo.testing.helpers import INF, OBS, d, txn

START, END = d("2026-09-01"), d("2026-09-30")


def books():  # type: ignore[no-untyped-def]
    return [
        txn("2026-09-01", (SAV, 100_000_00, OBS), (SALARY, -100_000_00, INF), payee="Acme Payroll"),
        txn("2026-09-02", (SAV, -30_000_00, OBS), (RENT, 30_000_00, INF), payee="Landlord"),
        txn("2026-09-03", (CARD, -2_500_00, OBS), (DINING, 2_500_00, INF), payee="Swiggy"),
        txn("2026-09-05", (CARD, -1_200_00, OBS), (DINING, 1_200_00, INF), payee="Swiggy"),
        txn("2026-09-06", (SAV, -400_00, OBS), (DINING, 400_00, INF), payee="Cafe"),
        txn("2026-09-07", (CARD, 300_00, OBS), (DINING, -300_00, INF), payee="Swiggy"),  # refund
        txn("2026-09-10", (SAV, -3_400_00, OBS), (CARD, 3_400_00, OBS), payee="Card bill"),
        txn("2026-09-11", (SAV, -5_000_00, OBS), (TO_PEOPLE, 5_000_00, INF), payee="Friend"),
        txn("2026-09-12", (SAV, 700_00, OBS), (FROM_PEOPLE, -700_00, INF), payee="Friend"),
        txn("2026-09-13", (SAV, -9_000_00, OBS), (TRANSIT, 9_000_00, OBS), payee="To other bank"),
        txn("2026-09-01", (CARD, -50_000_00, OBS), (OPEN, 50_000_00, OBS), payee="Opening balance"),
    ]


def test_a_card_bill_payment_is_a_transfer_not_spending() -> None:
    kinds = {(f.payee, f.account_id): f.bucket for f in flows(ACCOUNTS, books(), START, END)}
    assert kinds[("Card bill", SAV.id)] is Bucket.TRANSFER
    assert kinds[("Card bill", CARD.id)] is Bucket.TRANSFER
    assert kinds[("To other bank", SAV.id)] is Bucket.TRANSFER  # money in transit
    assert kinds[("Friend", SAV.id)] is Bucket.PEOPLE


def test_activity_separates_spending_people_transfers_income_and_refunds() -> None:
    by = {a.account_id: a for a in account_activity(ACCOUNTS, books(), START, END)}
    sav, card = by[SAV.id], by[CARD.id]
    assert (sav.spending, sav.people_out, sav.transfers_out) == (30_400_00, 5_000_00, 12_400_00)
    assert (sav.income, sav.people_in, sav.payments) == (100_000_00, 700_00, 5)
    assert sav.total_out == 47_800_00 and sav.transactions == 7
    assert (card.spending, card.refunds, card.transfers_in) == (3_700_00, 300_00, 3_400_00)
    assert card.total_out == 3_700_00 and card.payments == 2


def test_ranks_use_competition_order_and_skip_zero() -> None:
    assert ranks({SAV.id: 50, CARD.id: 50}) == {SAV.id: 1, CARD.id: 1}
    assert ranks({SAV.id: 50, CARD.id: 20}) == {SAV.id: 1, CARD.id: 2}
    assert ranks({SAV.id: 0, CARD.id: 9}) == {CARD.id: 1}


def test_opening_balances_are_not_payments() -> None:
    by = {a.account_id: a for a in account_activity(ACCOUNTS, books(), START, END)}
    assert by[CARD.id].total_out == 3_700_00 and by[CARD.id].payments == 2  # not 50,000 more
    assert not any(f.payee == "Opening balance" for f in find_flows(ACCOUNTS, books(), START, END))


def test_activity_outside_the_period_is_ignored() -> None:
    assert account_activity(ACCOUNTS, books(), d("2025-01-01"), d("2025-01-31")) == ()


def test_find_by_payee_text_sums_spending_and_leaves_out_refunds() -> None:
    hits = find_flows(ACCOUNTS, books(), START, END, text="swiggy")
    assert sorted(abs(f.amount) for f in hits) == [1_200_00, 2_500_00]
    refunds = find_flows(ACCOUNTS, books(), START, END, text="swiggy", direction="in")
    assert [abs(f.amount) for f in refunds] == [300_00]


def test_find_by_category_and_account_and_transfers_flag() -> None:
    dining = find_flows(ACCOUNTS, books(), START, END, category="dining")
    assert len(dining) == 3
    on_card = find_flows(ACCOUNTS, books(), START, END, account_ids={CARD.id})
    assert {f.payee for f in on_card} == {"Swiggy"}
    everything = find_flows(ACCOUNTS, books(), START, END, direction="any", include_transfers=True)
    assert any(f.payee == "Card bill" for f in everything)
    assert not any(f.payee == "Card bill" for f in find_flows(ACCOUNTS, books(), START, END))


def test_largest_first_and_month_totals() -> None:
    hits = find_flows(ACCOUNTS, books(), START, END)
    assert largest_first(hits)[0].payee == "Landlord"
    assert by_month(find_flows(ACCOUNTS, books(), None, None, text="cafe")) == [
        ("2026-09", 400_00, 1)
    ]


def test_regular_payments_need_three_months_and_say_whether_they_are_steady() -> None:
    txs = []
    for month, rent, swiggy in (
        ("07", 30_000_00, 900_00),
        ("08", 30_000_00, 2_500_00),
        ("09", 30_000_00, 400_00),
    ):
        txs.append(txn(f"2026-{month}-02", (SAV, -rent, OBS), (RENT, rent, INF), payee="Landlord"))
        txs.append(
            txn(f"2026-{month}-05", (CARD, -swiggy, OBS), (DINING, swiggy, INF), payee="Swiggy")
        )
    txs.append(txn("2026-09-20", (SAV, -77_00, OBS), (DINING, 77_00, INF), payee="One-off"))
    found = {
        r.payee: r for r in recurring_payments(ACCOUNTS, txs, ["2026-07", "2026-08", "2026-09"])
    }
    assert set(found) == {"Landlord", "Swiggy"}  # the one-off is not regular
    assert found["Landlord"].steady and found["Landlord"].average_monthly == 30_000_00
    assert not found["Swiggy"].steady and found["Swiggy"].average_monthly == 1_266_67
    assert found["Landlord"].months_seen == 3 and found["Landlord"].category == "Housing"
    assert recurring_payments(ACCOUNTS, txs, ["2026-07", "2026-08"]) == ()
