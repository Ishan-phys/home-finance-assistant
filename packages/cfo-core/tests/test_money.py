import pytest
from cfo.core.money import MoneyError, format_inr, paise_from_number, parse_paise


@pytest.mark.parametrize(
    ("text", "paise"),
    [
        ("1,00,000.50", 10000050),
        ("0", 0),
        ("12.5", 1250),
        ("-2,419.60", -241960),
        ("₹ 5", 500),
        ("2,58,017.40", 25801740),
        (" 7 ", 700),
    ],
)
def test_parse_indian_grouping(text: str, paise: int) -> None:
    assert parse_paise(text) == paise


@pytest.mark.parametrize("bad", ["1.234", "abc", "", "1.2.3", "--4", "1e5"])
def test_parse_rejects(bad: str) -> None:
    with pytest.raises(MoneyError):
        parse_paise(bad)


def test_spreadsheet_numbers_avoid_float_error() -> None:
    assert paise_from_number(2419.6) == 241960
    assert paise_from_number(1115.1) == 111510
    assert paise_from_number(5) == 500
    with pytest.raises(MoneyError):
        paise_from_number(1.005)


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (10000000, "₹1,00,000.00"),
        (0, "₹0.00"),
        (99, "₹0.99"),
        (-123456789, "-₹12,34,567.89"),
        (100000, "₹1,000.00"),
        (12345678900, "₹12,34,56,789.00"),
    ],
)
def test_format_inr(paise: int, text: str) -> None:
    assert format_inr(paise) == text
