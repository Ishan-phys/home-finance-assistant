import pytest
from cfo.doc import DocumentKind
from cfo.parse.base import ParseFailed, ValidationFailed
from cfo.parse.readers import read_document
from cfo.testing import FIXTURE_DIR


def load(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def test_format_comes_from_the_bytes_not_the_extension() -> None:
    # HDFC's card export is a legacy .xls workbook named .xlsx
    doc = read_document("hdfc_card_sep.xlsx", load("hdfc_card_sep.xlsx"))
    assert doc.kind is DocumentKind.SHEET and doc.rows
    # a PDF named .csv is still read as a PDF
    assert read_document("oops.csv", load("axis_card_sep.pdf")).kind is DocumentKind.TEXT


def test_pdf_becomes_lines_and_csv_becomes_rows() -> None:
    pdf = read_document("a.pdf", load("axis_card_sep.pdf"))
    assert any(line.startswith("Transaction Summary") for line in pdf.lines)
    csv = read_document("a.csv", load("hdfc_bank_sep.csv"))
    assert csv.kind is DocumentKind.SHEET and csv.rows[2][0] == "Txn Date"


def test_unreadable_and_oversized_files_are_rejected() -> None:
    with pytest.raises(ParseFailed, match="unsupported extension"):
        read_document("a.docx", b"x")
    with pytest.raises(ParseFailed):
        read_document("a.pdf", b"not a pdf")
    with pytest.raises(ValidationFailed, match="10 MiB"):
        read_document("a.csv", b"x" * (10 * 1024 * 1024 + 1))
