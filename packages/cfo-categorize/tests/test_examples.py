"""The owner's past decisions reach the model, masked, and only when they are relevant."""

from __future__ import annotations

import json
from collections.abc import Sequence

from cfo.categorize.categorizer import categorize
from cfo.categorize.examples import MAX_EXAMPLES, Example, pick_examples
from cfo.categorize.labels import default_labels
from cfo.categorize.port import Item
from cfo.redact import Masker

RENT = "UPI-[PERSON:5e31]-[VPA:19cd]-HDFC[ID:db1e]-[ID:d938]-RENT"
OTHER = "UPI-[PERSON:9a9a]-[VPA:0000]-SBIN[ID:2037]-[ID:6705]-UPI"


class Recording:
    def __init__(self) -> None:
        self.system = ""

    def complete(self, system: str, user: str) -> str:
        self.system = system
        return json.dumps({"items": []})


def _examples() -> list[Example]:
    return [
        Example(RENT, "debit", "Expenses:Housing"),
        Example("UPI-SWIGGY-[VPA:1111]-UPI", "debit", "Expenses:Food:Dining"),
    ]


def test_only_examples_sharing_a_person_token_or_word_are_chosen() -> None:
    picked = pick_examples(_examples(), [Item(RENT.replace("-RENT", "-MAY"), "debit")])
    assert [e.label for e in picked] == ["Expenses:Housing"]
    assert pick_examples(_examples(), [Item(OTHER, "debit")]) == []


def test_cap_and_recency() -> None:
    many = [Example(f"UPI-[PERSON:5e31]-N{n}", "debit", "Expenses:Housing") for n in range(30)]
    picked = pick_examples(many, [Item("UPI-[PERSON:5e31]-X", "debit")])
    assert len(picked) == MAX_EXAMPLES
    assert picked[0].description.endswith("N29")  # equal matches: newest first


def test_prompt_carries_the_owners_decision_and_it_is_masked() -> None:
    client = Recording()
    masker = Masker.from_plain(terms=["Vikram"], accounts=[], titles=[])
    categorize([Item(RENT, "debit")], default_labels(), client, masker, _examples())
    assert "[PERSON:5e31]" in client.system and "=> category_" in client.system
    assert "Expenses:Housing" not in client.system  # the real path never leaves; the key does
    assert "same person or business" in client.system


def test_no_relevant_example_means_no_block() -> None:
    client = Recording()
    categorize([Item(OTHER, "debit")], default_labels(), client, None, _examples())
    assert "already decided" not in client.system


def _unused(_: Sequence[object]) -> None: ...
