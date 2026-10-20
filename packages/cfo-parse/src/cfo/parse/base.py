"""File reading and the shared bank-statement parser (spec 4.4).

Adapters are configured, not coded: each declares the header it recognizes and which
columns carry what. They never call a model or compute metrics.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from cfo.core.money import MoneyError, paise_from_number, parse_paise
from cfo.doc import Document, DocumentKind

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20_000
HEADER_SEARCH_ROWS = 60


class ParseFailed(Exception):
    """PARSE_FAILED: extension, header, manual account, or no usable date."""


class PasswordRequired(ParseFailed):
    """PASSWORD_REQUIRED: the file is password-protected and no password was given."""


class PasswordInvalid(ParseFailed):
    """PASSWORD_INVALID: the password did not open the file."""


def require_kind(doc: Document, kind: DocumentKind, binding: str) -> None:
    """An adapter reads one kind of document; anything else is the wrong file for the account."""
    if doc.kind is not kind:
        wanted = "a spreadsheet or CSV" if kind is DocumentKind.SHEET else "a PDF"
        raise ParseFailed(f"header not recognized for {binding}: it reads {wanted}")


class ValidationFailed(Exception):
    """VALIDATION_FAILED: bad date or amount, or the file exceeds a limit."""


Grid = list[list[Any]]


@dataclass(frozen=True, slots=True)
class CanonicalRow:
    date: date
    amount: int  # signed paise: negative debit, positive credit
    raw_description: str
    # Set by adapters that know the other side is one of the owner's own accounts (Groww orders):
    # the row is posted against money in transit and never reaches the model.
    own_move: bool = False
    merchant: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedStatement:
    rows: tuple[CanonicalRow, ...]
    period_start: date | None = None
    period_end: date | None = None
    closing_balance: int | None = None  # paise, as stored (non-negative except overdrawn bank)
    balance_as_of: date | None = None
    amount_due: int | None = None
    due_date: date | None = None
    holdings_kind: str | None = None  # 'mutual_funds' or 'stocks' for Groww holdings files
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def valuation_date(self) -> date | None:
        """Balance date: the statement period end, or the latest row if that is later,
        or the latest row when the file has no period end."""
        return self.balance_as_of


def norm(cell: Any) -> str:
    return re.sub(r"\s+", " ", str(cell)).strip().lower() if cell is not None else ""


def is_blank(cell: Any) -> bool:
    return cell is None or (isinstance(cell, str) and not cell.strip())


def is_separator(cell: Any) -> bool:
    return isinstance(cell, str) and bool(cell.strip()) and set(cell.strip()) == {"*"}


_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%d %b %Y",
    "%d %b, %Y",
    "%d-%b-%Y",
    "%b %d %Y",
    "%d %b '%y",
)


def parse_date(cell: Any) -> date:
    if isinstance(cell, datetime):
        return cell.date()
    if isinstance(cell, date):
        return cell
    text = str(cell).strip().split(" / ")[0].strip()  # '21/08/2026 / 21:25' -> the date part
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationFailed(f"unparseable date: {text!r}")


def parse_amount(cell: Any, *, round_floats: bool = False) -> int | None:
    """Paise for a debit/credit/balance cell; None when the cell is empty.

    `round_floats` is for computed market values (units x price), which spreadsheets
    store with float noise; they are rounded half-even to paise instead of rejected.
    """
    if is_blank(cell):
        return None
    try:
        if round_floats and isinstance(cell, float):
            return int((Decimal(repr(cell)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
        if isinstance(cell, str):
            text = cell.strip().upper()
            sign = -1 if text.endswith("DR") else 1
            text = text.removesuffix("CR").removesuffix("DR").strip()
            return sign * parse_paise(text)
        if isinstance(cell, int | float | Decimal):
            return paise_from_number(cell)
    except MoneyError as exc:
        raise ValidationFailed(str(exc)) from exc
    raise ValidationFailed(f"unparseable amount: {cell!r}")


def clean_narration(cell: Any) -> str:
    """Strip surrounding whitespace and join the fixed-width wraps some exports insert
    (a newline plus one space in the middle of a word)."""
    text = "" if cell is None else str(cell)
    return re.sub(r"\r?\n ?", "", text).strip()


_PERIOD = re.compile(
    r"from\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*to\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    re.IGNORECASE,
)


def find_period(grid: Grid, limit: int = HEADER_SEARCH_ROWS) -> tuple[date, date] | None:
    for row in grid[:limit]:
        for cell in row:
            if isinstance(cell, str):
                m = _PERIOD.search(cell)
                if m:
                    return parse_date(m.group(1)), parse_date(m.group(2))
    return None


@dataclass(frozen=True, slots=True)
class BankLayout:
    """Which header names, in any column order, identify one institution's export."""

    binding: str
    date: Sequence[str]
    narration: Sequence[str]
    debit: Sequence[str]
    credit: Sequence[str]
    balance: Sequence[str]


class BankStatementAdapter:
    accepts = DocumentKind.SHEET

    def __init__(self, layout: BankLayout) -> None:
        self.layout = layout
        self.binding = layout.binding

    def _locate(self, grid: Grid) -> tuple[int, dict[str, int]] | None:
        lay = self.layout
        wanted = {
            "date": lay.date,
            "narration": lay.narration,
            "debit": lay.debit,
            "credit": lay.credit,
            "balance": lay.balance,
        }
        for i, row in enumerate(grid[:HEADER_SEARCH_ROWS]):
            cells = [norm(c) for c in row]
            cols: dict[str, int] = {}
            for key, names in wanted.items():
                hit = next((j for j, c in enumerate(cells) if c in names), None)
                if hit is None:
                    break
                cols[key] = hit
            else:
                return i, cols
        return None

    def parse(self, doc: Document) -> ParsedStatement:
        require_kind(doc, self.accepts, self.binding)
        grid = doc.grid
        found = self._locate(grid)
        if found is None:
            raise ParseFailed(f"header not recognized for {self.binding}")
        header_row, cols = found

        rows: list[CanonicalRow] = []
        balances: list[tuple[int, date, int | None, int]] = []  # (line, date, balance, signed)
        started = False
        for offset, raw in enumerate(grid[header_row + 1 :], start=header_row + 2):
            cells = list(raw) + [None] * (max(cols.values()) + 1 - len(raw))
            if all(is_blank(c) for c in cells):
                if started:
                    break
                continue
            if any(is_separator(c) for c in cells if not is_blank(c)):
                if started:
                    break
                continue
            date_cell = cells[cols["date"]]
            if is_blank(date_cell):
                raise ValidationFailed(f"row {offset}: missing date")
            posted = parse_date(date_cell)
            debit = parse_amount(cells[cols["debit"]])
            credit = parse_amount(cells[cols["credit"]])
            if (debit is None) == (credit is None):
                raise ValidationFailed(f"row {offset}: exactly one of debit or credit is required")
            if (debit or credit or 0) < 0:
                raise ValidationFailed(f"row {offset}: negative debit or credit")
            signed = -debit if debit is not None else credit
            assert signed is not None
            started = True
            rows.append(CanonicalRow(posted, signed, clean_narration(cells[cols["narration"]])))
            balances.append((offset, posted, parse_amount(cells[cols["balance"]]), signed))

        if not rows:
            raise ParseFailed("no usable date: the statement has no transactions")
        if len(rows) > MAX_ROWS:
            raise ValidationFailed("file has more than 20,000 data rows")

        period = find_period(grid)
        warnings: list[str] = []
        closing = next((b for _, _, b, _ in reversed(balances) if b is not None), None)
        prev: int | None = None
        for line, _, bal, signed in balances:
            if bal is None:
                continue
            if prev is not None and prev + signed != bal:
                warnings.append(f"row {line}: running balance does not reconcile")
                break
            prev = bal
        latest = max(r.date for r in rows)
        as_of = max(latest, period[1]) if period else latest
        if closing is None:
            warnings.append("statement has no closing balance")
        return ParsedStatement(
            rows=tuple(rows),
            period_start=period[0] if period else None,
            period_end=period[1] if period else None,
            closing_balance=closing,
            balance_as_of=as_of if closing is not None else None,
            warnings=tuple(warnings),
        )
