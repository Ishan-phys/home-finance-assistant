"""A ModelClient that answers from fixed mappings: demos and tests without a live model."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from cfo.categorize.labels import OWN_MOVE_LABEL
from cfo.core.chart import DEFAULT_CATEGORIES

_LABEL_LINE = re.compile(r"^(\S+): (.+?) — ", re.MULTILINE)
_NAMES = {c.path: c.name for c in DEFAULT_CATEGORIES} | {OWN_MOVE_LABEL.key: OWN_MOVE_LABEL.name}
_VARIABLE = re.compile(r"\[[A-Z_]+(?::[0-9a-f]+)?\]|\d{6,}")


def shape(text: str) -> str:
    """A narration with its tokens and long numbers blanked, so a seed written for the original
    narration still matches the redacted one, whatever salt produced the tokens."""
    return _VARIABLE.sub("#", text)


class SeedClient:
    """Answers from `{description: {merchant, label}}` (label = account path), matching on `shape`. Descriptions it
    does not know are omitted, which leaves them Uncategorized, as a real model miss would."""

    def __init__(
        self,
        seed: dict[str, dict[str, str]],
        prepare: Callable[[str], str] = lambda s: s,
    ) -> None:
        """`prepare` turns a seed narration into the form the ledger stores, for example by
        redacting it, so a seed written for the original text still matches."""
        self.seed = {shape(prepare(k)): v for k, v in seed.items()}

    @classmethod
    def from_file(cls, path: Path, prepare: Callable[[str], str] = lambda s: s) -> SeedClient:
        return cls(json.loads(path.read_text()), prepare)

    def complete(self, system: str, user: str) -> str:
        # Category keys may be aliased (masking on), so answer by the category's name.
        keys = {m.group(2): m.group(1) for m in _LABEL_LINE.finditer(system)}
        items = []
        for line in user.splitlines():
            number, rest = line.split(". ", 1)
            description = rest.split(" ", 1)[1] if rest.startswith("(") else rest
            hit = self.seed.get(shape(description))
            if hit:
                key = keys.get(_NAMES.get(hit["label"], ""), hit["label"])
                items.append({"id": int(number), "merchant": hit["merchant"], "category": key})
        return json.dumps({"items": items})
