"""Axis Bank credit card statement (PDF only; spec 4.4).

Axis issues the statement as a PDF with a text layer. The layout is a payment summary
(total due, minimum due, due date), a statement summary (month, limit, opening balance),
then one line per transaction: '08 Sep '26 Cashback credit Aug26-POS:435 ₹ 435.00 Credit'.

The statement carries no period end, only a statement month, so the balance is dated by the
latest transaction. A total due that is zero or negative (the card is in credit) is kept as
the balance and creates no payment obligation. Password-protected PDFs are unlocked before reading (see unlock.py).
"""

from __future__ import annotations

import re

from cfo.doc import Document, DocumentKind
from cfo.parse.base import (
    MAX_ROWS,
    CanonicalRow,
    ParsedStatement,
    ParseFailed,
    ValidationFailed,
    parse_amount,
    parse_date,
    require_kind,
)

_AMOUNT = r"-?[\d,]+\.\d{2}"
_CUR = r"(?:₹|Rs\.?|\x00)"  # some PDF fonts lose the rupee glyph
_SUMMARY = re.compile(
    rf"{_CUR}\s*({_AMOUNT})\s+{_CUR}\s*({_AMOUNT})\s+(\d{{1,2}} \w{{3}} '\d{{2}})"
)
_MONTH = re.compile(rf"\b([A-Z][a-z]{{2}} \d{{4}})\s+{_CUR}\s*({_AMOUNT})\s+{_CUR}\s*({_AMOUNT})")
_ROW = re.compile(
    rf"^(\d{{1,2}} \w{{3}} '\d{{2}})\s+(.+?)\s+{_CUR}\s*({_AMOUNT})\s+(Debit|Credit)\s*$"
)


class AxisCreditCardAdapter:
    binding = "axis_credit_card"
    accepts = DocumentKind.TEXT

    def parse(self, doc: Document) -> ParsedStatement:
        require_kind(doc, self.accepts, self.binding)
        text = doc.full_text
        if "Credit Card" not in text or "Transaction Summary" not in text:
            raise ParseFailed("header not recognized for axis_credit_card")

        summary = _SUMMARY.search(text)
        month = _MONTH.search(text)
        if summary is None or month is None:
            raise ParseFailed("header not recognized for axis_credit_card: payment summary missing")
        total_due = parse_amount(summary.group(1))
        due_date = parse_date(summary.group(3))
        opening = parse_amount(month.group(3))
        assert total_due is not None and opening is not None

        rows: list[CanonicalRow] = []
        for line in text.splitlines():
            m = _ROW.match(line.strip())
            if m is None:
                continue
            amount = parse_amount(m.group(3))
            assert amount is not None
            rows.append(
                CanonicalRow(
                    parse_date(m.group(1)),
                    amount if m.group(4) == "Credit" else -amount,  # purchase = debit
                    m.group(2).strip(),
                )
            )
        if len(rows) > MAX_ROWS:
            raise ValidationFailed("file has more than 20,000 data rows")
        if not rows:
            raise ParseFailed("no usable date: the statement has no transactions")

        warnings: list[str] = []
        debits = -sum(r.amount for r in rows if r.amount < 0)
        credits = sum(r.amount for r in rows if r.amount > 0)
        if opening + debits - credits != total_due:
            warnings.append(
                "transactions do not reconcile to the statement balance; a line may not have been read"
            )
        latest = max(r.date for r in rows)
        return ParsedStatement(
            rows=tuple(rows),
            closing_balance=total_due,
            balance_as_of=latest,
            amount_due=total_due,
            due_date=due_date,
            warnings=tuple(warnings),
        )
