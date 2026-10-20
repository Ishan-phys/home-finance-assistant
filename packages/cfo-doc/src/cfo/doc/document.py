from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class DocumentKind(StrEnum):
    SHEET = "sheet"  # a workbook's first sheet, or a CSV: rows of typed cells
    TEXT = "text"  # a PDF's text layer: lines of text


@dataclass(frozen=True, slots=True)
class Document:
    """Immutable. A sheet holds rows of cells that are text, numbers, dates, or None; a text
    document holds lines. Transforming a document returns a new one."""

    kind: DocumentKind
    rows: tuple[tuple[Any, ...], ...] = ()
    lines: tuple[str, ...] = ()

    @classmethod
    def sheet(cls, rows: list[list[Any]] | tuple[tuple[Any, ...], ...]) -> Document:
        return cls(DocumentKind.SHEET, rows=tuple(tuple(r) for r in rows))

    @classmethod
    def text(cls, lines: list[str] | tuple[str, ...]) -> Document:
        return cls(DocumentKind.TEXT, lines=tuple(lines))

    @property
    def grid(self) -> list[list[Any]]:
        """The rows as mutable lists, for code that indexes cells."""
        return [list(r) for r in self.rows]

    @property
    def full_text(self) -> str:
        if self.kind is DocumentKind.TEXT:
            return "\n".join(self.lines)
        return "\n".join(str(c) for row in self.rows for c in row if isinstance(c, str))

    def map_text(self, fn: Callable[[str], str]) -> Document:
        """Apply `fn` to every piece of text and leave typed numbers and dates untouched."""
        if self.kind is DocumentKind.TEXT:
            return Document(self.kind, lines=tuple(fn(line) for line in self.lines))
        return Document(
            self.kind,
            rows=tuple(tuple(fn(c) if isinstance(c, str) else c for c in row) for row in self.rows),
        )

    def text_pieces(self) -> list[str]:
        """Every string in the document, in order."""
        if self.kind is DocumentKind.TEXT:
            return list(self.lines)
        return [c for row in self.rows for c in row if isinstance(c, str)]


# Cell types a reader may produce, for readers and type checkers.
Cell = str | int | float | date | datetime | None
