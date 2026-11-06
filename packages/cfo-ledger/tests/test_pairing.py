from datetime import date

from cfo.ledger.pairing import PAIR_WINDOW_DAYS, Half, find_pairs
from cfo.testing.helpers import uid

SAV, CARD, FD = uid(101), uid(102), uid(103)
D = date.fromisoformat


def test_pairs_equal_and_opposite_within_window() -> None:
    a = Half(uid(1), SAV, D("2026-09-04"), 1626800)
    b = Half(uid(2), CARD, D("2026-09-06"), -1626800)
    assert find_pairs([b, a]) == [(uid(1), uid(2))]  # the side money left from comes first


def test_same_account_never_pairs() -> None:
    assert (
        find_pairs([Half(uid(1), SAV, D("2026-09-04"), 5), Half(uid(2), SAV, D("2026-09-04"), -5)])
        == []
    )


def test_outside_window_or_unequal_never_pairs() -> None:
    late = D("2026-09-04").toordinal() + PAIR_WINDOW_DAYS + 1
    assert (
        find_pairs(
            [Half(uid(1), SAV, D("2026-09-04"), 5), Half(uid(2), CARD, date.fromordinal(late), -5)]
        )
        == []
    )
    assert (
        find_pairs([Half(uid(1), SAV, D("2026-09-04"), 5), Half(uid(2), CARD, D("2026-09-04"), -6)])
        == []
    )


def test_equal_amounts_pair_one_to_one_deterministically() -> None:
    day = D("2026-09-10")
    halves = [
        Half(uid(1), SAV, day, 500000),
        Half(uid(2), SAV, day, 500000),
        Half(uid(3), FD, day, -500000),
    ]
    first = find_pairs(halves)
    assert len(first) == 1 and first == find_pairs(list(reversed(halves)))


def test_closest_dates_pair_first() -> None:
    halves = [
        Half(uid(1), SAV, D("2026-09-01"), 100),
        Half(uid(2), CARD, D("2026-09-03"), -100),
        Half(uid(3), FD, D("2026-09-02"), -100),
    ]
    assert find_pairs(halves) == [(uid(1), uid(3))]


def test_card_matches_need_the_same_card_amount_and_window() -> None:
    from cfo.ledger.pairing import find_card_matches

    axis, hdfc = uid(201), uid(202)
    recorded = [
        Half(uid(1), axis, D("2026-10-30"), 1211186),
        Half(uid(2), hdfc, D("2026-10-30"), 612900),
    ]
    lines = [
        Half(uid(3), hdfc, D("2026-10-31"), 1211186),  # right amount, wrong card
        Half(uid(4), axis, D("2026-10-31"), 1211185),  # right card, off by a paisa
        Half(uid(5), axis, D("2026-11-30"), 1211186),  # right card and amount, too late
        Half(uid(6), hdfc, D("2026-11-01"), 612900),
    ]
    assert find_card_matches(recorded, lines) == [(uid(2), uid(6))]


def test_card_matches_are_one_to_one_closest_first_and_order_free() -> None:
    from cfo.ledger.pairing import find_card_matches

    card = uid(201)
    recorded = [Half(uid(1), card, D("2026-10-20"), 500), Half(uid(2), card, D("2026-10-29"), 500)]
    lines = [Half(uid(3), card, D("2026-10-30"), 500)]
    first = find_card_matches(recorded, lines)
    assert first == [(uid(2), uid(3))] == find_card_matches(list(reversed(recorded)), lines)
