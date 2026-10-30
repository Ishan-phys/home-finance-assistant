"""The System-1 categorizer port: label each distinct description with one of the ledger's own
categories, or leave it unresolved."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from cfo.categorize.categorizer import CategorizationResult, GenerativeCategorizer, ModelClient
from cfo.categorize.examples import Example, mask_examples, pick_examples
from cfo.categorize.labels import (
    OWN_MOVE_LABEL,
    Label,
    NarrationMasker,
    Way,
    default_labels,
    labels_for,
    mask_labels,
)

__all__ = [
    "OWN_MOVE_LABEL",
    "Categorizer",
    "Example",
    "Item",
    "Label",
    "MaskedCategorizer",
    "NarrationMasker",
    "as_categorizer",
    "default_labels",
    "labels_for",
]


@dataclass(frozen=True, slots=True)
class Item:
    """One distinct, redacted description, with which way the money moved."""

    description: str
    direction: Way | None = None


@runtime_checkable
class Categorizer(Protocol):
    def categorize(
        self, items: Sequence[Item], labels: Sequence[Label], examples: Sequence[Example] = ()
    ) -> CategorizationResult:
        """Label each item with one of `labels`; `examples` are the owner's past decisions on
        similar lines. Anything the model could not label confidently is left out of `mappings`
        and listed in `unresolved`. Never raises for a model failure."""
        ...


class MaskedCategorizer:
    """Masks narrations and label text before a System-1 categorizer sees them, and keys the
    answers back on the stored narrations."""

    def __init__(self, inner: Categorizer, masker: NarrationMasker) -> None:
        self.inner, self.masker = inner, masker

    def categorize(
        self, items: Sequence[Item], labels: Sequence[Label], examples: Sequence[Example] = ()
    ) -> CategorizationResult:
        back: dict[str, str] = {}
        masked: list[Item] = []
        for item in items:
            text = self.masker.narration(item.description)
            back.setdefault(text, item.description)
            masked.append(Item(text, item.direction))
        sent, keys = mask_labels(labels, self.masker)
        shown = mask_examples(
            pick_examples(examples, items),
            self.masker,
            {path: key for key, path in keys.items()},
        )
        result = self.inner.categorize(masked, sent, shown)
        mappings = {
            back.get(k, k): replace(m, lookup_key=back.get(k, k), label=keys[m.label])
            for k, m in result.mappings.items()
            if m.label in keys
        }
        unresolved = tuple(back.get(d, d) for d in result.unresolved)
        return replace(result, mappings=mappings, unresolved=unresolved)


def as_categorizer(
    client: Categorizer | ModelClient | None, masker: NarrationMasker | None = None
) -> Categorizer | None:
    """Accept a System-1 categorizer, or wrap a generative model client behind the port. With a
    masker, only masked narrations and label text leave the machine either way."""
    if client is None:
        return None
    if isinstance(client, Categorizer):
        return client if masker is None else MaskedCategorizer(client, masker)
    return GenerativeCategorizer(client, masker)
