from __future__ import annotations

from typing import Protocol

from cfo.doc import Document, DocumentKind
from cfo.parse.axis import AxisCreditCardAdapter
from cfo.parse.banks import HDFC_BANK, SBI_BANK
from cfo.parse.base import ParsedStatement
from cfo.parse.cards import HdfcCreditCardAdapter
from cfo.parse.groww import GrowwHoldingsAdapter


class Adapter(Protocol):
    binding: str
    accepts: DocumentKind

    def parse(self, doc: Document) -> ParsedStatement: ...


_ALL: tuple[Adapter, ...] = (
    HDFC_BANK,
    SBI_BANK,
    HdfcCreditCardAdapter(),
    AxisCreditCardAdapter(),
    GrowwHoldingsAdapter(),
)
ADAPTERS: dict[str, Adapter] = {a.binding: a for a in _ALL}
