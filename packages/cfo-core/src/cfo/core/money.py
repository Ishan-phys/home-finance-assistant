"""Paise parsing and Indian-grouped formatting. All money is integer paise."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_PLAIN = re.compile(r"^-?\d+(\.\d+)?$")


class MoneyError(ValueError):
    pass


def parse_paise(text: str) -> int:
    """Parse '1,00,000.50' (optionally with a rupee sign or leading minus) to paise.

    Rejects anything with more than two fractional digits.
    """
    cleaned = text.strip().replace(",", "").replace("₹", "").replace(" ", "")
    if not _PLAIN.match(cleaned):
        raise MoneyError(f"not an amount: {text!r}")
    whole, _, frac = cleaned.partition(".")
    if len(frac) > 2:
        raise MoneyError(f"more than two fractional digits: {text!r}")
    negative = whole.startswith("-")
    paise = int(whole.lstrip("-") or "0") * 100 + int(frac.ljust(2, "0") or "0")
    return -paise if negative else paise


def paise_from_number(value: float | int | Decimal) -> int:
    """Convert a spreadsheet numeric cell to paise without float arithmetic.

    The shortest repr of a float (e.g. 2419.6) is read as decimal text, so binary
    float error never reaches the ledger.
    """
    if isinstance(value, bool):
        raise MoneyError("boolean is not an amount")
    try:
        text = format(Decimal(repr(value)) if isinstance(value, float) else Decimal(value), "f")
    except InvalidOperation as exc:
        raise MoneyError(f"not an amount: {value!r}") from exc
    return parse_paise(text)


def _group_indian(digits: str) -> str:
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join([*parts, tail])


def format_inr(paise: int) -> str:
    """Format paise as '₹1,00,000.00' (negative as '-₹1,00,000.00')."""
    sign = "-" if paise < 0 else ""
    rupees, p = divmod(abs(paise), 100)
    return f"{sign}₹{_group_indian(str(rupees))}.{p:02d}"
