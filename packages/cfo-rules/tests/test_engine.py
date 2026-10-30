import pytest
from cfo.core.ids import new_id
from cfo.rules import MatchMode, Rule, first_match, normalize, suggest_match_text


def rule(text: str, *, mode=MatchMode.CONTAINS, way="any", target="Expenses:Housing", position=0):
    return Rule(new_id(), text, text, mode, way, target, position)


def test_contains_is_case_and_space_insensitive() -> None:
    r = rule("urban  company")
    assert first_match([r], "UPI-URBAN COMPANY LIMITE-PAYTM", "debit") is r


def test_starts_with_only_matches_prefix() -> None:
    r = rule("NEFT", mode=MatchMode.STARTS_WITH)
    assert first_match([r], "NEFT CR-ACME", "credit") is r
    assert first_match([r], "UPI-NEFT-ACME", "credit") is None


def test_way_filters_direction() -> None:
    r = rule("refund", way="credit")
    assert first_match([r], "REFUND FROM SHOP", "debit") is None
    assert first_match([r], "REFUND FROM SHOP", "credit") is r


def test_lowest_position_wins() -> None:
    late, early = rule("cred", position=5), rule("cred", position=1)
    assert first_match([late, early], "UPI-CRED CLUB", "debit") is early


@pytest.mark.parametrize("text", ["", "   ", "\t\n"])
def test_blank_match_text_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        rule(text)


def test_normalize_collapses_whitespace_and_case() -> None:
    assert normalize("  A\tb \n C ") == "a b c"


def test_suggest_drops_refs_and_handles() -> None:
    s = "UPI-URBAN COMPANY LIMITE-PAYTM-[VPA:06e6]-YESB0PTMUPI-[ID:1552]-UPI"
    assert suggest_match_text(s) == "URBAN COMPANY LIMITE"


def test_suggest_keeps_person_token() -> None:
    s = "UPI-[PERSON:5e31]-[VPA:19cd]-HDFC[ID:db1e]-[ID:d938]-RENT"
    assert suggest_match_text(s) == "[PERSON:5e31]"


def test_suggest_falls_back_to_first_words() -> None:
    assert suggest_match_text("CASHBACK CREDIT AUG26-POS:435") == "CASHBACK CREDIT AUG26"
