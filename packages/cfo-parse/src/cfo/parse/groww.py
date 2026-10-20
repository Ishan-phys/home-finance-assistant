"""Groww holdings exports (spec 4.4): mutual-fund holdings and stock holdings.

Both are snapshots, not ledgers: no transactions, one valuation (the summed current
market value) dated by the 'as on' line. Because each file reports only its own asset
type, mutual funds and stocks are separate accounts, so one upload never replaces the
other's balance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cfo.doc import Document, DocumentKind
from cfo.parse.base import (
    HEADER_SEARCH_ROWS,
    CanonicalRow,
    Grid,
    ParsedStatement,
    ParseFailed,
    ValidationFailed,
    is_blank,
    norm,
    parse_amount,
    parse_date,
    require_kind,
)

_AS_ON = re.compile(r"as on\s+(\d{1,4}[-/]\d{1,2}[-/]\d{1,4})", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class HoldingsLayout:
    name: str
    kind: str
    name_header: str
    value_header: str


MUTUAL_FUNDS = HoldingsLayout("mutual funds", "mutual_funds", "scheme name", "current value")
STOCKS = HoldingsLayout("stocks", "stocks", "stock name", "closing value")


_ORDERS_PERIOD = re.compile(
    r"transactions from\s+(\w{3} \d{1,2} \d{4})\s+to\s+(\w{3} \d{1,2} \d{4})", re.IGNORECASE
)
_ORDER_HEADER = ("scheme name", "transaction type", "nav", "amount", "date")
_BUY = {"purchase", "buy", "sip"}
_SELL = {"redeem", "sell", "redemption"}


class GrowwHoldingsAdapter:
    """Groww exports: holdings snapshots (mutual funds, stocks) and mutual fund order history."""

    binding = "groww"
    accepts = DocumentKind.SHEET
    layouts = (MUTUAL_FUNDS, STOCKS)

    def parse(self, doc: Document) -> ParsedStatement:
        require_kind(doc, self.accepts, self.binding)
        grid = doc.grid
        orders = self._parse_orders(grid)
        if orders is not None:
            return orders
        for layout in self.layouts:
            found = self._locate(grid, layout)
            if found is not None:
                return self._parse(grid, layout, *found)
        raise ParseFailed("header not recognized for groww")

    @staticmethod
    def _locate(grid: Grid, layout: HoldingsLayout) -> tuple[int, int] | None:
        for i, row in enumerate(grid[:HEADER_SEARCH_ROWS]):
            cells = [norm(c) for c in row]
            if layout.name_header in cells and layout.value_header in cells:
                return i, cells.index(layout.value_header)
        return None

    @staticmethod
    def _parse(
        grid: Grid, layout: HoldingsLayout, header_row: int, value_col: int
    ) -> ParsedStatement:
        as_on = None
        for row in grid[:HEADER_SEARCH_ROWS]:
            for cell in row:
                m = _AS_ON.search(cell) if isinstance(cell, str) else None
                if m:
                    as_on = parse_date(m.group(1))
        if as_on is None:
            raise ParseFailed("no usable date: holdings file has no 'as on' date")

        total = 0
        count = 0
        for offset, raw in enumerate(grid[header_row + 1 :], start=header_row + 2):
            cells = list(raw) + [None] * (value_col + 1 - len(raw))
            if all(is_blank(c) for c in cells):
                if count:
                    break
                continue
            value = parse_amount(cells[value_col], round_floats=True)
            if value is None or value < 0:
                raise ValidationFailed(f"row {offset}: missing or negative {layout.value_header}")
            total += value
            count += 1
        if count == 0:
            raise ParseFailed("no holdings in file")
        return ParsedStatement(
            rows=(),
            period_end=as_on,
            closing_balance=total,
            balance_as_of=as_on,
            holdings_kind=layout.kind,
        )

    @staticmethod
    def _parse_orders(grid: Grid) -> ParsedStatement | None:
        """Order history is a ledger: a purchase moves money into the account (a credit) and
        a redemption moves it out (a debit). Rows are Investments with the scheme as merchant,
        and no balance is reported, so the holdings file supplies the valuation."""
        header = None
        for i, row in enumerate(grid[:HEADER_SEARCH_ROWS]):
            cells = [norm(c) for c in row]
            if all(name in cells for name in _ORDER_HEADER):
                header = (i, {name: cells.index(name) for name in _ORDER_HEADER}, cells)
                break
        if header is None:
            return None
        header_row, cols, cells = header
        units_col = cells.index("units") if "units" in cells else None

        period_end = None
        period_start = None
        for row in grid[:HEADER_SEARCH_ROWS]:
            for cell in row:
                m = _ORDERS_PERIOD.search(cell) if isinstance(cell, str) else None
                if m:
                    period_start, period_end = parse_date(m.group(1)), parse_date(m.group(2))

        rows: list[CanonicalRow] = []
        for offset, raw in enumerate(grid[header_row + 1 :], start=header_row + 2):
            row = list(raw) + [None] * (max(cols.values()) + 1 - len(raw))
            if all(is_blank(c) for c in row):
                if rows:
                    break
                continue
            scheme = str(row[cols["scheme name"]]).strip()
            kind = norm(row[cols["transaction type"]])
            amount = parse_amount(row[cols["amount"]])
            if kind not in _BUY | _SELL:
                raise ValidationFailed(f"row {offset}: unknown transaction type {kind!r}")
            if not scheme or amount is None or amount <= 0:
                raise ValidationFailed(f"row {offset}: missing scheme or amount")
            posted = parse_date(row[cols["date"]])
            units = str(row[units_col]).strip() if units_col is not None else ""
            nav = str(row[cols["nav"]]).strip()
            description = f"{kind.upper()} {scheme} {units} units @ {nav}"
            rows.append(
                CanonicalRow(
                    posted,
                    amount if kind in _BUY else -amount,
                    description,
                    own_move=True,
                    merchant=scheme,
                )
            )
        if not rows:
            raise ParseFailed("no usable date: the order history has no orders")
        return ParsedStatement(
            rows=tuple(rows),
            period_start=period_start,
            period_end=period_end or max(r.date for r in rows),
        )
