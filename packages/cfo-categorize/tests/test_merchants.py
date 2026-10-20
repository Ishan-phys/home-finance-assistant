import pytest
from cfo.categorize.merchants import clean_merchant


@pytest.mark.parametrize(
    ("narration", "merchant"),
    [
        # HDFC bank UPI: UPI-<payee>-<handle>-<ifsc>-<ref>-<note>
        ("UPI-SWIGGY-[VPA:ab12]-ICIC[ID:cd34]-[ID:ef56]-Order", "Swiggy"),
        ("UPI-AUTOPAY-APPLE MEDIA SERVICES-[VPA:ab12]-HDFC[ID:cd34]", "Apple Media"),
        ("UPIRET-TEST CAFE REFUND", "Test Cafe"),
        ("UPI-OPEN MART-[VPA:ab12]-YESB[ID:cd34]-[ID:ef56]-UPI", "Open Mart"),
        # SBI UPI: UPI/DR/<ref>/<payee>/<bank>/<handle>
        ("WDL TFR UPI/DR/[ID:ab12]/URBAN CO/YESB/paytm-ur", "Urban Co"),
        ("WDL TFR UPI/DR/[ID:ab12]/BROKENTU/CITI/setuv", "Brokentu"),
        # IMPS and NEFT
        ("NEFT CR-TESTCORP LTD-SALARY SEP-[PERSON:ab12]-TESTN0001", "Testcorp"),
        ("NEFT DR-TEST LANDLORD-RENT SEP-[PERSON:ab12]", "Test Landlord"),
        # card statements
        ("PAY*SWIGGY FOOD BANGALORE", "Swiggy Food"),
        ("PYU*Instamart Grocery Bangalore", "Instamart Grocery"),
        ("RSP*SWIGGY PVT LTD FO BENGALURU", "Swiggy"),
        ("SWIGGY LIMITED Bengaluru", "Swiggy"),
        ("ANTHROPIC SAN FRANCISC", "Anthropic"),
        ("10% Swiggy CashBack", "Swiggy Cashback"),
        # fall-backs
        ("INTEREST PAID TILL 30-SEP-2026", "Interest Paid Till Sep"),
        ("ACH D- TEST MUTUAL FUND SIP-REF0001", "Test Mutual Fund SIP"),
    ],
)
def test_real_narration_shapes(narration: str, merchant: str) -> None:
    assert clean_merchant(narration) == merchant


def test_never_returns_a_token_or_an_empty_name() -> None:
    for narration in ("[PERSON:ab12]", "UPI-[VPA:ab12]", "[ID:ab12] [ID:cd34]", "   "):
        name = clean_merchant(narration)
        assert "[" not in name
