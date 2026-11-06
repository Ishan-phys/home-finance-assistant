from cfo.metrics.card_payments import card_choices, payable_amount
from cfo.testing.books import ACCOUNTS, CARD, DINING, FUND, SAV, TRANSIT, UNCAT_IN, UNCAT_OUT
from cfo.testing.helpers import INF, OBS, OWN, SYS, AccountType, d, imp, real, txn

OTHER = real(AccountType.CREDIT_CARD, "Axis Flipkart", institution="Axis", id=20)
ALL = [*ACCOUNTS, OTHER]


def test_money_out_of_a_bank_account_with_a_guessed_other_side_can_pay_a_card() -> None:
    for guess in (UNCAT_OUT, TRANSIT, DINING):
        assert payable_amount(ALL, txn("2026-10-30", (SAV, -500, OBS), (guess, 500, INF))) == 500


def test_everything_else_cannot() -> None:
    assert payable_amount(ALL, txn("2026-10-30", (SAV, 500, OBS), (UNCAT_IN, -500, INF))) is None
    assert payable_amount(ALL, txn("2026-10-30", (FUND, -500, OBS), (UNCAT_OUT, 500, INF))) is None
    matched = txn("2026-10-30", (SAV, -500, OBS), (CARD, 500, OBS))
    assert payable_amount(ALL, matched) is None
    opening = txn("2026-10-01", (SAV, 500, SYS), (UNCAT_IN, -500, SYS))
    assert payable_amount(ALL, opening) is None


def test_a_recorded_card_payment_can_still_be_moved_to_another_card() -> None:
    recorded = txn("2026-10-30", (SAV, -500, OBS), (CARD, 500, OWN))
    assert payable_amount(ALL, recorded) == 500


def test_choices_put_the_card_that_owes_the_amount_first_and_mark_the_current_one() -> None:
    owes = txn("2026-09-02", (CARD, -612900, OBS), (DINING, 612900, INF))
    pay = txn("2026-10-30", (SAV, -612900, OBS), (UNCAT_OUT, 612900, INF))
    got = card_choices(ALL, [owes, pay], [], pay)
    assert [c.account_id for c in got] == [CARD.id, OTHER.id]
    assert [(c.owed, c.suggested, c.current) for c in got] == [
        (612900, True, False),
        (0, False, False),
    ]
    recorded = txn("2026-10-30", (SAV, -612900, OBS), (OTHER, 612900, OWN))
    assert (
        next(c for c in card_choices(ALL, [owes, recorded], [], recorded) if c.current).account_id
        == OTHER.id
    )


def test_choices_suggest_the_card_whose_bill_has_that_much_left() -> None:
    card_import = imp(CARD, "2026-09-20", amount_due=500, due_date=d("2026-10-05"))
    pay = txn("2026-10-30", (SAV, -500, OBS), (UNCAT_OUT, 500, INF))
    assert [c.suggested for c in card_choices(ALL, [pay], [card_import], pay)] == [True, False]


def test_no_choices_for_a_row_that_cannot_pay_a_card() -> None:
    credit = txn("2026-10-30", (SAV, 500, OBS), (UNCAT_IN, -500, INF))
    assert card_choices(ALL, [credit], [], credit) == ()
