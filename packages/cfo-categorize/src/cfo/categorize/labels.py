"""The categories a ledger offers the model: an account path, a name and the owner's one-line
description of what the category is for."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from cfo.core.chart import DEFAULT_CATEGORIES, IN_TRANSIT
from cfo.core.types import Direction

Way = Literal["debit", "credit"]


class NarrationMasker(Protocol):
    """Anything that can mask a narration before it is sent (cfo-redact's Masker does)."""

    def narration(self, text: str) -> str: ...


@dataclass(frozen=True, slots=True)
class Label:
    key: str  # the account path a row is posted against
    name: str
    description: str
    direction: Literal["debit", "credit", "any"]


OWN_MOVE_LABEL = Label(
    IN_TRANSIT,
    "Own account or investment",
    "Money moved between the person's own accounts: transfers to own savings, credit card bill "
    "payments, mutual funds, SIPs, stocks, deposits.",
    "any",
)


def labels_for(way: Way | None, labels: Sequence[Label]) -> list[Label]:
    """What one row may be labelled. Money out takes spending categories only; money in takes
    income categories and, for refunds, spending ones."""
    if way == "debit":
        return [x for x in labels if x.direction in ("debit", "any")]
    return list(labels)


def default_labels() -> list[Label]:
    """The default categories, for demos and tests; uploads use the ledger's own."""
    return [
        Label(c.path, c.name, c.description, "credit" if c.direction is Direction.IN else "debit")
        for c in DEFAULT_CATEGORIES
    ] + [OWN_MOVE_LABEL]


def mask_labels(
    labels: Sequence[Label], masker: NarrationMasker | None
) -> tuple[list[Label], dict[str, str]]:
    """Owner-written names and descriptions leave the machine only through the masker, and keys
    (account paths, which carry category names) are replaced by opaque ones. Returns the labels
    to send and a map from sent key back to account path."""
    if masker is None:
        return list(labels), {x.key: x.key for x in labels}
    sent: list[Label] = []
    back: dict[str, str] = {}
    for n, x in enumerate(labels, start=1):
        key = "own_move" if x.key == OWN_MOVE_LABEL.key else f"category_{n}"
        back[key] = x.key
        sent.append(
            replace(
                x,
                key=key,
                name=masker.narration(x.name),
                description=masker.narration(x.description),
            )
        )
    return sent, back
