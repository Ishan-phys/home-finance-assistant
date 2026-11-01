"""Owner rules: "if the narration contains X, post it to Y". Pure and local, so it runs on the
original narration without that text going anywhere. No database, no model, no regex: a rule is
one piece of text, a match mode and an optional direction, and the lowest position wins."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from cfo.core.ids import Id

Way = Literal["any", "debit", "credit"]


class MatchMode(StrEnum):
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"


def normalize(text: str) -> str:
    return " ".join(text.casefold().split())


@dataclass(frozen=True, slots=True)
class Rule:
    id: Id
    label: str
    match_text: str  # as the owner typed it; compared normalised
    mode: MatchMode
    way: Way
    target: str  # the account path the counter-posting goes to (money in transit for a transfer)
    position: int  # lower runs first
    builtin: bool = False

    def __post_init__(self) -> None:
        if not normalize(self.match_text):
            raise ValueError("a rule needs some text to match; an empty one would match everything")

    def matches(self, narration: str, way: Literal["debit", "credit"]) -> bool:
        if self.way != "any" and self.way != way:
            return False
        text, wanted = normalize(narration), normalize(self.match_text)
        return text.startswith(wanted) if self.mode is MatchMode.STARTS_WITH else wanted in text


def first_match(
    rules: Iterable[Rule], narration: str, way: Literal["debit", "credit"]
) -> Rule | None:
    """The matching rule with the lowest position (ties broken by id, so order never matters)."""
    hits = [r for r in rules if r.matches(narration, way)]
    return min(hits, key=lambda r: (r.position, str(r.id)), default=None)


_PREFIX = re.compile(r"^(?:UPIRET|UPI|IMPS|NEFT|RTGS)[-/ ]", re.I)
_PERSON = re.compile(r"\[PERSON:[0-9a-f]+\]")
_OTHER_TOKEN = re.compile(r"\[[A-Z_]+(?::[0-9a-f]+)?\]")
_SKIP = {"AUTOPAY", "MANDATE", "COLLECT", "UPI", "DR", "CR", "PAYMENT", "PAY", "SI", "NA"}


def _noise(segment: str) -> bool:
    s = segment.strip()
    return (
        not s
        or (_OTHER_TOKEN.search(s) is not None and _PERSON.search(s) is None)
        or re.fullmatch(r"[\d\W_]+", s) is not None
        or s.upper() in _SKIP
        or re.fullmatch(r"[A-Z]{4}\d?[A-Z0-9]*\d[A-Z0-9]*", s) is not None  # an IFSC or a handle
    )


def suggest_match_text(narration: str) -> str:
    """A starting point for "always do this": the payee part of a narration, without references,
    handles or digits. The owner edits it before saving."""
    text = narration.strip()
    if _PREFIX.match(text):
        for seg in re.split(r"[-/]", _PREFIX.sub("", text)):
            if not _noise(seg):
                return seg.strip()
    first = re.split(r"[-/]", text)[0]
    return " ".join(_OTHER_TOKEN.sub(" ", first).split()) or text
