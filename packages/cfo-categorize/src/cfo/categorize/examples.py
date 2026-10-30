"""The owner's own past decisions, offered to the model as examples.

A redacted narration hides who a person payee is, but the token for them is the same every time.
So when the owner has said "[PERSON:5e31] is Housing", showing the model that line (masked like
everything else that leaves the machine) teaches it who they are. Examples are chosen by the words
and person tokens they share with the lines being asked about, most recent first.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from cfo.categorize.labels import NarrationMasker, Way

if TYPE_CHECKING:
    from cfo.categorize.port import Item

MAX_EXAMPLES = 20
_TOKENS = re.compile(r"\[PERSON:[0-9a-f]+\]|[A-Za-z]{3,}")
_OTHER_MARKS = re.compile(r"\[(?!PERSON:)[A-Z_]+(?::[0-9a-f]+)?\]")
_GENERIC = frozenset({"upi", "imps", "neft", "rtgs", "pos", "ach", "payment", "transfer", "ref"})


@dataclass(frozen=True, slots=True)
class Example:
    """One line the owner categorized: the redacted narration and the label they chose."""

    description: str
    direction: Way | None
    label: str  # an account path, or the key sent to the model once labels are masked


def _tokens(text: str) -> set[str]:
    """Words and person tokens. Other redaction marks ([VPA:..], [ID:..]) differ every time and
    say nothing about who the line is for, so they are dropped first."""
    return {t.casefold() for t in _TOKENS.findall(_OTHER_MARKS.sub(" ", text))} - _GENERIC


def pick_examples(
    examples: Sequence[Example], items: Sequence[Item], limit: int = MAX_EXAMPLES
) -> list[Example]:
    """Up to `limit` examples that share a word or person token with the items, best match first
    and, among equals, the most recent (`examples` run oldest to newest)."""
    wanted: set[str] = set()
    for item in items:
        wanted |= _tokens(item.description)
    scored = [(len(_tokens(e.description) & wanted), n, e) for n, e in enumerate(examples)]
    hits = sorted((x for x in scored if x[0] > 0), key=lambda x: (-x[0], -x[1]))
    return [e for *_, e in hits[:limit]]


def mask_examples(
    examples: Sequence[Example], masker: NarrationMasker | None, key_for_path: Mapping[str, str]
) -> list[Example]:
    """Examples as they may leave the machine: text masked, label replaced by the key the model
    was given. One whose category is not on offer (retired) is dropped."""
    return [
        replace(
            e,
            description=masker.narration(e.description) if masker else e.description,
            label=key_for_path[e.label],
        )
        for e in examples
        if e.label in key_for_path
    ]


def render_examples(examples: Sequence[Example]) -> str:
    """The block appended to a prompt, or nothing when there are no examples."""
    if not examples:
        return ""
    lines = "\n".join(
        f"- ({e.direction or 'unknown'}) {e.description} => {e.label}" for e in examples
    )
    return (
        "\n\nThe owner already decided these lines. Follow them for similar lines. A "
        "[PERSON:xxxx] token is always the same person or business, so what the owner chose for a "
        f"token applies to every line with it:\n{lines}"
    )
