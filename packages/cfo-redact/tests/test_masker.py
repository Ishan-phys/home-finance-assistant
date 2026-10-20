import pytest
from cfo.redact.masker import REDACTED, AliasTarget, Masker, TitleTarget
from cfo.redact.names import NAMES


def test_the_two_spec_examples() -> None:
    m = Masker.build()
    assert m.narration("UPI/9876543210/Rahul") == "UPI/[REDACTED]/[REDACTED]"
    assert m.narration("UPI/Swiggy/Order") == "UPI/Swiggy/Order"  # merchant words stay


def test_the_steps_run_in_order() -> None:
    m = Masker.build(terms=["Asha Verma"])
    # 1 owner term, 2 VPA, 3 digit run, 4 name words
    text = "UPI-Asha Verma-asha.v@okaxis-HDFC0001234-4012345678-Dinner with Rohan"
    assert (
        m.narration(text)
        == f"UPI-{REDACTED}-{REDACTED}-HDFC{REDACTED}-{REDACTED}-Dinner with {REDACTED}"
    )


def test_vpa_and_digit_boundaries() -> None:
    m = Masker.build()
    assert m.narration("pay q412345678@ybl now") == f"pay {REDACTED} now"
    assert m.narration("ref 12345 ok") == "ref 12345 ok"  # five digits stay
    assert m.narration("ref 123456 ok") == f"ref {REDACTED} ok"  # six are redacted
    assert m.narration("INR 40,000.00") == "INR 40,000.00"  # a formatted amount is not a number run


def test_real_statement_shapes() -> None:
    m = Masker.build()
    hdfc = "UPI-ARJUN MEHTA-MEHTA852-7@OKSBI-IDFB0040101-412345678901-UPI"
    out = m.narration(hdfc)
    assert "OKSBI" not in out and "MEHTA" not in out and "412345678901" not in out
    sbi = "DEP TFR   0011223344556 OF Mr. ARJUN MEHTA AT 01234 PBB"
    out = m.narration(sbi)
    assert "ARJUN" not in out and "MEHTA" not in out and "0011223344556" not in out


@pytest.mark.parametrize(
    "merchant",
    [
        "Swiggy",
        "Zomato",
        "Amazon",
        "Ola",
        "Uber",
        "Apple",
        "Netflix",
        "Airtel",
        "Flipkart",
        "Instamart",
        "Anthropic",
        "Starbucks",
        "Bigbasket",
        "Reliance",
        "Tata",
        "Bajaj",
        "Myntra",
        "Cred",
    ],
)
def test_merchant_words_are_never_on_the_name_lists(merchant: str) -> None:
    assert merchant.lower() not in NAMES


def test_owner_terms_are_case_insensitive_and_longest_first() -> None:
    m = Masker.build(terms=["arjun", "arjun mehta"])
    assert m.narration("Mr ARJUN MEHTA and Arjun") == f"Mr {REDACTED} and {REDACTED}"


def accounts() -> list[AliasTarget]:
    return [
        AliasTarget("01", "HDFC Savings", "Liquid_Account", "HDFC Bank", "XXXX1234"),
        AliasTarget("02", "My Regalia Card", "Credit_Card"),
        AliasTarget("03", "Joint SBI", "Liquid_Account"),
        AliasTarget("04", "Groww Funds", "Investment_Account"),
    ]


def title(key: str, text: str, prefix: str = "Obligation") -> TitleTarget:
    return TitleTarget(key, text, prefix)


def test_aliases_are_stable_and_numbered_by_id() -> None:
    a = Masker.build(
        accounts=accounts(),
        titles=[title("2", "Maid"), title("1", "Rent"), title("3", "Salary Acme", "Income_Source")],
    )
    assert a.aliases == {
        "HDFC Savings": "Liquid_Account_1",
        "My Regalia Card": "Credit_Card_1",
        "Joint SBI": "Liquid_Account_2",
        "Groww Funds": "Investment_Account_1",
        "HDFC Bank": "Institution_1",
        "XXXX1234": "Account_Reference_1",
        "Rent": "Obligation_1",
        "Maid": "Obligation_2",
        "Salary Acme": "Income_Source_1",
    }
    b = Masker.build(
        accounts=list(reversed(accounts())),
        titles=[title("1", "Rent"), title("2", "Maid"), title("3", "Salary Acme", "Income_Source")],
    )
    assert a.aliases == b.aliases  # the same ledger always yields the same map


def test_text_aliases_then_masks_and_reply_is_unaliased() -> None:
    m = Masker.build(accounts=accounts(), titles=[title("1", "Rent")])
    sent = m.text("HDFC Savings paid Rent via UPI/9876543210/Rahul")
    assert sent == f"Liquid_Account_1 paid Obligation_1 via UPI/{REDACTED}/{REDACTED}"
    assert m.unalias("Obligation_1 is due from Liquid_Account_1; Liquid_Account_10 is unknown") == (
        "Rent is due from HDFC Savings; Liquid_Account_10 is unknown"
    )


def test_payload_masks_strings_deeply_and_leaves_numbers() -> None:
    m = Masker.build(accounts=accounts())
    payload = {
        "safe": {"paise": 5575729000, "formatted": "₹55,75,729.00"},
        "coverage": [{"account": "HDFC Savings", "state": "current"}],
        "ok": True,
        "n": None,
    }
    out = m.payload(payload)
    assert out["safe"] == payload["safe"]  # amounts stay numeric
    assert out["coverage"][0] == {"account": "Liquid_Account_1", "state": "current"}
    assert out["ok"] is True and out["n"] is None
