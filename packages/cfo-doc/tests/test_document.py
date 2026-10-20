from datetime import date

from cfo.doc import Document, DocumentKind


def test_sheet_map_text_leaves_typed_cells_alone() -> None:
    doc = Document.sheet([["Name", "ASHA", 5.5], [date(2026, 9, 1), None, "x"]])
    out = doc.map_text(str.lower)
    assert out.rows == (("name", "asha", 5.5), (date(2026, 9, 1), None, "x"))
    assert doc.rows[0][1] == "ASHA"  # the original is untouched: documents are immutable


def test_text_document_maps_every_line_and_joins() -> None:
    doc = Document.text(["Total ₹ 5", "Due 10 Oct"])
    assert doc.kind is DocumentKind.TEXT
    assert doc.map_text(str.upper).lines == ("TOTAL ₹ 5", "DUE 10 OCT")
    assert doc.full_text == "Total ₹ 5\nDue 10 Oct"
    assert doc.text_pieces() == ["Total ₹ 5", "Due 10 Oct"]


def test_sheet_full_text_skips_numbers() -> None:
    assert Document.sheet([["a", 1, "b"]]).full_text == "a\nb"


def test_grid_is_a_mutable_copy() -> None:
    doc = Document.sheet([["a", "b"]])
    grid = doc.grid
    grid[0][0] = "z"
    assert doc.rows == (("a", "b"),)
