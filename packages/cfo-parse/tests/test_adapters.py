import re
from pathlib import Path

import pytest
from cfo.parse.base import ParseFailed, ValidationFailed
from cfo.parse.readers import read_document
from cfo.parse.registry import ADAPTERS
from cfo.testing import FIXTURE_DIR
from cfo.testing.helpers import d

FIXTURES = FIXTURE_DIR


def parse_file(binding: str, filename: str, content: bytes):  # type: ignore[no-untyped-def]
    return ADAPTERS[binding].parse(read_document(filename, content))


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_hdfc_xls_layout() -> None:
    p = parse_file("hdfc_bank", "hdfc_bank_sep.xls", load("hdfc_bank_sep.xls"))
    assert len(p.rows) == 9
    assert (p.period_start, p.period_end) == (d("2026-09-01"), d("2026-09-30"))
    salary, rent = p.rows[0], p.rows[2]
    assert (
        salary.amount == 150_000_00 and rent.amount == -30_000_00
    )  # debit negative, credit positive
    assert p.rows[6].amount == -1_850_50
    # the last row is dated Oct 1, after the period end: the balance is as of that row
    assert p.closing_balance == 192_455_50
    assert p.balance_as_of == d("2026-10-01")
    assert p.warnings == ()


def test_hdfc_csv_variant_matches_xls() -> None:
    xls = parse_file("hdfc_bank", "a.xls", load("hdfc_bank_sep.xls"))
    csv = parse_file("hdfc_bank", "a.csv", load("hdfc_bank_sep.csv"))
    assert xls.rows == csv.rows and xls.closing_balance == csv.closing_balance


def test_sbi_xlsx_layout_and_wrap_join() -> None:
    p = parse_file("sbi_bank", "sbi_bank_sep.xlsx", load("sbi_bank_sep.xlsx"))
    assert [r.amount for r in p.rows] == [-105_00, -304_00, 5000_00, 2573_00]
    assert p.rows[3].raw_description == "INTEREST CREDIT"  # "INTERES\n T CREDIT" rejoined
    assert "\n" not in p.rows[0].raw_description and p.rows[0].raw_description.startswith("WDL TFR")
    assert (p.closing_balance, p.balance_as_of) == (265_181_40, d("2026-09-30"))


def test_cp1252_csv_fallback() -> None:
    body = "Statement From : 01/09/2026 To : 30/09/2026\nTxn Date,Narration,Withdrawals,Deposits,Closing Balance\n"
    body += "01/09/2026,CAFÉ,10.00,,90.00\n"
    p = parse_file("hdfc_bank", "x.csv", body.encode("cp1252"))
    assert p.rows[0].raw_description == "CAFÉ"


@pytest.mark.parametrize(
    ("binding", "name"),
    [("sbi_bank", "hdfc_bank_sep.xls"), ("hdfc_bank", "sbi_bank_sep.xlsx")],
)
def test_other_institutions_export_is_rejected(binding: str, name: str) -> None:
    with pytest.raises(ParseFailed, match="header not recognized"):
        parse_file(binding, name, load(name))


def test_unsupported_extension_and_manual_binding() -> None:
    with pytest.raises(ParseFailed, match="extension"):
        read_document("statement.docx", b"x")
    assert "manual" not in ADAPTERS  # manual accounts have no binding and accept no upload


def _csv(*rows: str) -> bytes:
    head = "Txn Date,Narration,Withdrawals,Deposits,Closing Balance\n"
    return (head + "\n".join(rows) + "\n").encode()


@pytest.mark.parametrize(
    "rows",
    [
        ["32/09/2026,X,1.00,,5.00"],  # bad date
        ["01/09/2026,X,1.005,,5.00"],  # three fractional digits
        ["01/09/2026,X,abc,,5.00"],  # not an amount
        ["01/09/2026,X,1.00,2.00,5.00"],  # both debit and credit
        ["01/09/2026,X,,,5.00"],  # neither
        ["01/09/2026,X,1.00,,5.00", ",Y,2.00,,3.00"],  # one bad row rejects the whole file
    ],
)
def test_whole_file_rejection(rows: list[str]) -> None:
    with pytest.raises(ValidationFailed):
        parse_file("hdfc_bank", "x.csv", _csv(*rows))


def test_no_transactions_is_parse_failed() -> None:
    with pytest.raises(ParseFailed, match="no usable date"):
        parse_file("hdfc_bank", "x.csv", _csv())


def test_row_limit_and_size_limit() -> None:
    with pytest.raises(ValidationFailed, match="10 MiB"):
        read_document("x.csv", b"a" * (10 * 1024 * 1024 + 1))
    many = _csv(*["01/09/2026,X,1.00,,5.00"] * 20_001)
    with pytest.raises(ValidationFailed, match="20,000"):
        parse_file("hdfc_bank", "x.csv", many)


def test_missing_balance_warns_and_unreconciled_balance_warns() -> None:
    no_bal = b"Txn Date,Narration,Withdrawals,Deposits,Closing Balance\n01/09/2026,X,1.00,,\n"
    p = parse_file("hdfc_bank", "x.csv", no_bal)
    assert p.closing_balance is None and "no closing balance" in p.warnings[0]
    bad = _csv("01/09/2026,X,1.00,,99.00", "02/09/2026,Y,1.00,,10.00")
    assert any("reconcile" in w for w in parse_file("hdfc_bank", "x.csv", bad).warnings)


PHONE = re.compile(r"(?<!\d)\d{10}(?!\d)")
UPI_ID = re.compile(r"[\w.\-]{2,}@[A-Za-z][\w]{1,}")


@pytest.mark.parametrize(
    "path",
    sorted(p for p in FIXTURES.iterdir() if p.suffix in {".csv", ".xlsx", ".xls"}),
    ids=lambda p: p.name,
)
def test_fixture_hygiene(path: Path) -> None:
    """Fixtures are synthetic: no UPI ids and no ten-digit phone numbers."""
    text = "\n".join(
        str(c)
        for row in read_document(path.name, path.read_bytes()).rows
        for c in row
        if c is not None
    )
    assert not PHONE.search(text), f"phone-like number in {path.name}"
    assert not UPI_ID.search(text), f"UPI-like id in {path.name}"


def test_hdfc_card_layout_and_mislabeled_extension() -> None:
    # the real export is a legacy .xls workbook saved with an .xlsx name
    p = parse_file("hdfc_credit_card", "hdfc_card_sep.xlsx", load("hdfc_card_sep.xlsx"))
    assert len(p.rows) == 6  # the Reward Points section is not read as transactions
    purchase, cashback, payment = p.rows[0], p.rows[1], p.rows[4]
    assert purchase.amount == -138_00  # a purchase is a debit
    assert cashback.amount == 93_20 and payment.amount == 16_268_00  # credits
    assert purchase.raw_description == "TEST FOOD ORDER CITY"
    assert (p.period_end, p.due_date) == (d("2026-09-20"), d("2026-10-10"))
    assert (p.amount_due, p.closing_balance, p.balance_as_of) == (
        10_064_00,
        10_064_00,
        d("2026-09-20"),
    )
    assert p.warnings == ()


def test_hdfc_card_missing_due_and_total_mismatch_warn() -> None:
    csv = (
        b"Purchases / Debits\n99.00\n"
        b"Transaction type,Primary / Addon Customer Name,Date & Time,Description,AMT,Debit / Credit\n"
        b"Domestic,X,01/09/2026 / 10:00,SHOP,10.00,\n"
    )
    p = parse_file("hdfc_credit_card", "x.csv", csv)
    assert p.amount_due is None and p.closing_balance is None
    assert any("amount due" in w for w in p.warnings)
    assert any("purchases total" in w for w in p.warnings)


def test_groww_mutual_fund_holdings_sum_with_float_noise() -> None:
    p = parse_file("groww", "h.xlsx", load("groww_mf_holdings.xlsx"))
    assert p.rows == ()  # a snapshot, not a ledger
    assert p.closing_balance == 112_000_50  # 62,000.25 + 50,000.25
    assert (p.balance_as_of, p.period_end) == (d("2026-10-03"), d("2026-10-03"))


def test_groww_stock_holdings() -> None:
    p = parse_file("groww", "s.xlsx", load("groww_stocks_holdings.xlsx"))
    assert p.closing_balance == 85_365_29 and p.balance_as_of == d("2026-10-02")


def test_groww_rejects_a_bank_statement() -> None:
    with pytest.raises(ParseFailed, match="header not recognized"):
        parse_file("groww", "a.xls", load("hdfc_bank_sep.xls"))
    with pytest.raises(ParseFailed, match="header not recognized"):
        parse_file("hdfc_credit_card", "a.xls", load("hdfc_bank_sep.xls"))


def test_axis_pdf_layout() -> None:
    p = parse_file("axis_credit_card", "axis_card_sep.pdf", load("axis_card_sep.pdf"))
    assert [r.amount for r in p.rows] == [100_00, -1_500_00, -250_00, -250_00, 3_000_00]
    assert p.rows[0].raw_description == "Cashback credit Aug26-POS:100"
    assert (p.closing_balance, p.amount_due, p.due_date) == (3_900_00, 3_900_00, d("2026-10-03"))
    assert p.period_end is None and p.balance_as_of == d("2026-09-08")  # no period end in the PDF
    assert p.warnings == ()  # 5,000 + 2,000 - 100 - 3,000 reconciles


def test_axis_pdf_rejections() -> None:
    with pytest.raises(ParseFailed, match="PDF"):
        parse_file("axis_credit_card", "statement.csv", b"x")
    with pytest.raises(ParseFailed, match="cannot read the PDF"):
        parse_file("axis_credit_card", "s.pdf", b"not a pdf")
    other = _pdf(["Some Other Bank Statement", "08 Sep '26 THING Rs 1.00 Debit"])
    with pytest.raises(ParseFailed, match="header not recognized"):
        parse_file("axis_credit_card", "s.pdf", other)


def test_axis_credit_balance_is_kept_and_mismatch_warns() -> None:
    from fixtures.build_fixtures import axis_pdf_lines  # noqa: PLC0415

    rows = [("08 Sep '26", "REFUND", "150.00", "Credit")]
    credit = _pdf(axis_pdf_lines("50.00", "-100.00", rows))
    p = parse_file("axis_credit_card", "s.pdf", credit)
    assert (p.closing_balance, p.amount_due, p.warnings) == (-100_00, -100_00, ())  # card in credit
    off = parse_file("axis_credit_card", "s.pdf", _pdf(axis_pdf_lines("50.00", "-90.00", rows)))
    assert any("reconcile" in w for w in off.warnings)


def _pdf(lines: list[str]) -> bytes:
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in lines:
        c.drawString(40, y, line.replace("₹", "Rs"))
        y -= 14
    c.save()
    return buf.getvalue()


def test_groww_order_history() -> None:
    p = parse_file("groww", "o.xlsx", load("groww_mf_orders.xlsx"))
    assert [r.amount for r in p.rows] == [4_999_00, -49_106_00, 4_999_00, 4_999_00]  # buy = credit
    assert all(r.own_move for r in p.rows)
    assert p.rows[0].merchant == "Test Gold Fund Direct Growth"
    assert p.rows[0].raw_description == "PURCHASE Test Gold Fund Direct Growth 109.26 units @ 45.76"
    assert (p.period_start, p.period_end) == (d("2026-04-01"), d("2026-10-03"))
    assert p.closing_balance is None and p.warnings == ()  # holdings supply the balance
    assert [r.date for r in p.rows].count(d("2026-08-26")) == 2  # twin rows kept for dedup


def test_axis_regexes_accept_the_real_rupee_glyph() -> None:
    from cfo.parse.axis import _ROW, _SUMMARY  # noqa: PLC0415

    row = _ROW.match("08 Sep '26 Cashback credit Aug26-POS:435 ₹ 435.00 Credit")
    assert row and row.group(3) == "435.00" and row.group(4) == "Credit"
    assert _SUMMARY.search("₹ -8,935.00 ₹ -0.00 03 Oct '26")
