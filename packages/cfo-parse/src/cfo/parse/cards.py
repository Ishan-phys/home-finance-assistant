"""HDFC credit card statement layout (spec 4.4).

The export is a key/value preamble (Payment Due Date, Statement Date, Total Amount Due),
an account summary, then a transaction table whose date cell reads '21/08/2026 / 21:25'
and whose last column is 'Cr' for credits and empty for purchases. Despite the .xlsx
name it is a legacy .xls workbook; `read_grid` sniffs the bytes.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from cfo.doc import Document, DocumentKind
from cfo.parse.base import (
    HEADER_SEARCH_ROWS,
    MAX_ROWS,
    CanonicalRow,
    Grid,
    ParsedStatement,
    ParseFailed,
    ValidationFailed,
    clean_narration,
    is_blank,
    norm,
    parse_amount,
    parse_date,
    require_kind,
)

_HEADER = {
    "type": "transaction type",
    "date": "date & time",
    "description": "description",
    "amount": "amt",
    "dc": "debit / credit",
}
ROUNDING_TOLERANCE = 100  # totals are rounded to the rupee; transactions are not


def _value_right_of(grid: Grid, label: str) -> Any:
    for row in grid[:HEADER_SEARCH_ROWS]:
        if row and norm(row[0]) == label:
            return next((c for c in row[1:] if not is_blank(c)), None)
    return None


def _summary_cell(grid: Grid, label: str) -> int | None:
    """In the account summary, the value sits on the row below its label, same column."""
    for i, row in enumerate(grid[:HEADER_SEARCH_ROWS]):
        for j, cell in enumerate(row):
            if norm(cell) == label and i + 1 < len(grid) and j < len(grid[i + 1]):
                return parse_amount(grid[i + 1][j])
    return None


class HdfcCreditCardAdapter:
    binding = "hdfc_credit_card"
    accepts = DocumentKind.SHEET

    def parse(self, doc: Document) -> ParsedStatement:
        require_kind(doc, self.accepts, self.binding)
        grid = doc.grid
        header_row, cols = self._locate(grid)

        rows: list[CanonicalRow] = []
        for offset, raw in enumerate(grid[header_row + 1 :], start=header_row + 2):
            cells = list(raw) + [None] * (max(cols.values()) + 1 - len(raw))
            if all(is_blank(c) for c in cells):
                continue
            if is_blank(cells[cols["date"]]):
                break  # next section (Reward Points Summary, GST Summary, ...)
            posted = parse_date(cells[cols["date"]])
            amount = parse_amount(cells[cols["amount"]])
            if amount is None or amount < 0:
                raise ValidationFailed(f"row {offset}: missing or negative amount")
            marker = norm(cells[cols["dc"]])
            if marker not in ("", "dr", "cr"):
                raise ValidationFailed(f"row {offset}: unknown debit/credit marker {marker!r}")
            signed = amount if marker == "cr" else -amount  # purchase = debit, payment = credit
            rows.append(CanonicalRow(posted, signed, clean_narration(cells[cols["description"]])))
        if len(rows) > MAX_ROWS:
            raise ValidationFailed("file has more than 20,000 data rows")

        statement_date = _value_right_of(grid, "statement date")
        period_end = parse_date(statement_date) if statement_date else None
        if not rows and period_end is None:
            raise ParseFailed("no usable date: the statement has no transactions or statement date")

        warnings: list[str] = []
        due_text = _value_right_of(grid, "total amount due")
        amount_due = parse_amount(due_text)
        due_raw = _value_right_of(grid, "payment due date")
        due_date: date | None = parse_date(due_raw) if due_raw else None
        if amount_due is None or due_date is None:
            warnings.append("card statement has no amount due or due date")
        if amount_due is None:
            warnings.append("statement has no closing balance")

        purchases = _summary_cell(grid, "purchases / debits")
        payments = _summary_cell(grid, "payment / credit")
        debits = -sum(r.amount for r in rows if r.amount < 0)
        credits = sum(r.amount for r in rows if r.amount > 0)
        if purchases is not None and purchases != debits:
            warnings.append("transaction debits do not match the statement's purchases total")
        if payments is not None and payments != credits:
            warnings.append("transaction credits do not match the statement's payments total")

        as_of = period_end or max(r.date for r in rows)
        return ParsedStatement(
            rows=tuple(rows),
            period_end=period_end,
            closing_balance=amount_due,
            balance_as_of=as_of if amount_due is not None else None,
            amount_due=amount_due,
            due_date=due_date,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _locate(grid: Grid) -> tuple[int, dict[str, int]]:
        for i, row in enumerate(grid[:HEADER_SEARCH_ROWS]):
            cells = [norm(c) for c in row]
            if all(name in cells for name in _HEADER.values()):
                return i, {key: cells.index(name) for key, name in _HEADER.items()}
        raise ParseFailed("header not recognized for hdfc_credit_card")
