"""Read file bytes into a `Document` (spec 4.12.1, stage 2).

The format is detected from the bytes, not the extension, because exports are sometimes
mislabeled (HDFC card statements are legacy .xls workbooks saved as .xlsx).
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import PurePath
from typing import Any

from cfo.doc import Document
from cfo.parse.base import (
    HEADER_SEARCH_ROWS,
    MAX_BYTES,
    MAX_ROWS,
    ParseFailed,
    ValidationFailed,
)

SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls", ".pdf")
_OLE2 = b"\xd0\xcf\x11\xe0"
_ZIP = b"PK\x03\x04"
_PDF = b"%PDF"


def read_document(filename: str, content: bytes) -> Document:
    """Decode a .csv, .xlsx or .xls (first sheet), or a PDF's text layer."""
    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ParseFailed(
            f"unsupported extension {ext or '(none)'}; use .csv, .xlsx, .xls or (Axis) .pdf"
        )
    if len(content) > MAX_BYTES:
        raise ValidationFailed("file is larger than 10 MiB")
    try:
        doc = _read(ext, content)
    except (ParseFailed, ValidationFailed):
        raise
    except Exception as exc:  # corrupt or mislabeled file
        raise ParseFailed(f"cannot read {ext} file: {exc}") from exc
    if len(doc.rows) > MAX_ROWS + HEADER_SEARCH_ROWS:
        raise ValidationFailed("file has more than 20,000 rows")
    return doc


def _sniff(ext: str, content: bytes) -> str:
    if content.startswith(_PDF):
        return ".pdf"
    if content.startswith(_OLE2):
        return ".xls"
    if content.startswith(_ZIP):
        return ".xlsx"
    return ext


def _read(ext: str, content: bytes) -> Document:
    ext = _sniff(ext, content)
    if ext == ".pdf":
        return _read_pdf(content)
    if ext == ".csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("cp1252")
        return Document.sheet([list(r) for r in csv.reader(io.StringIO(text))])
    if ext == ".xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        return Document.sheet([list(r) for r in wb.worksheets[0].iter_rows(values_only=True)])
    import xlrd

    sheet = xlrd.open_workbook(file_contents=content).sheet_by_index(0)
    rows: list[list[Any]] = []
    for r in range(sheet.nrows):
        row: list[Any] = []
        for c in range(sheet.ncols):
            ctype = sheet.cell_type(r, c)
            value = sheet.cell_value(r, c)
            row.append(None if ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK) else value)
        rows.append(row)
    return Document.sheet(rows)


def _read_pdf(content: bytes) -> Document:
    import pdfplumber
    from pdfplumber.utils.exceptions import PdfminerException

    logging.getLogger("pdfminer").setLevel(logging.ERROR)  # font warnings are noise
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except PdfminerException as exc:
        raise ParseFailed("cannot read the PDF") from exc
    return Document.text(text.splitlines())
