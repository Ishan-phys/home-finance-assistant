"""Claude categorization of distinct statement descriptions (spec 3.4, 4.5).

The model only proposes a cleaned merchant and one standard category per description.
Anything it gets wrong or omits leaves that description Uncategorized; nothing here can
fail an upload. A model client is a one-method protocol, so tests use a scripted fake.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Protocol

from cfo.categorize.labels import OWN_MOVE_LABEL, Label, NarrationMasker, labels_for, mask_labels
from cfo.core.types import MappingSource, MerchantMapping

BATCH_SIZE = 50

SYSTEM_PROMPT = (
    "You categorize Indian bank and credit card statement narrations. "
    "For each numbered narration, marked (debit) for money out or (credit) for money in, return "
    "a cleaned merchant name (the business, without reference numbers, UPI handles, or card "
    "digits) and exactly one category key from the list below. A refund or reversal of a purchase is a "
    "credit: give it the category named Refunds when the list has one. Money between the person's own accounts, a credit card bill "
    "payment, and investments take the key {own}. If none fits, leave the line out by omitting "
    "its id. Reply with JSON only, in this shape: "
    '{{"items": [{{"id": 1, "merchant": "Swiggy", "category": "Expenses:Food:Dining"}}]}}. '
    "Private details were removed and appear as [REDACTED] or tokens such as [PERSON:ab12]; "
    "never guess them. A narration that is only a person-to-person transfer has no merchant: "
    'use the merchant "Personal transfer".\n\nCategories (key: name — what it is for):\n{labels}'
)


if TYPE_CHECKING:
    from cfo.categorize.port import Item

REDACTION_MARKS = (
    "[REDACTED]",
    "[PERSON:",
    "[VPA:",
    "[ID:",
    "[PHONE:",
    "[EMAIL:",
    "[PAN:",
    "[ADDRESS",
)


class ModelClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the model's text reply. May raise if the model is unreachable."""
        ...


class AnthropicClient:
    """The generative path: a plain Claude call, used when the Decisions API is unavailable."""

    def __init__(self, model: str, *, max_tokens: int = 4096) -> None:
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        import anthropic

        message = anthropic.Anthropic(max_retries=1, timeout=60).messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in message.content if block.type == "text")


@dataclass(frozen=True, slots=True)
class CategorizationResult:
    mappings: dict[str, MerchantMapping] = field(default_factory=dict)  # keyed by description
    unresolved: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    input_tokens: int = 0  # billed input, for usage counts; never content


def _batches(items: Sequence[Item]) -> Iterable[Sequence[Item]]:
    for i in range(0, len(items), BATCH_SIZE):
        yield items[i : i + BATCH_SIZE]


log = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _parse(
    reply: str, batch: Sequence[Item], allowed: Sequence[set[str]]
) -> dict[str, MerchantMapping]:
    """Valid items from one reply. Raises ValueError when the reply is not usable JSON."""
    data = json.loads(_FENCE.sub("", reply.strip()))
    items = data["items"]
    if not isinstance(items, list):
        raise ValueError("items is not a list")
    out: dict[str, MerchantMapping] = {}
    for item in items:
        try:
            idx = int(item["id"]) - 1
            merchant = str(item["merchant"]).strip()
            label = str(item["category"]).strip()
        except (KeyError, TypeError, ValueError):
            continue  # a missing field: that description stays Uncategorized
        if not (0 <= idx < len(batch)) or not merchant or label not in allowed[idx]:
            continue  # out of range, blank, or not a category this line was offered
        description = batch[idx].description
        if any(
            mark in merchant for mark in REDACTION_MARKS
        ):  # the model echoed a hole: there is no merchant to name
            merchant = "Personal transfer"
        out.setdefault(
            description, MerchantMapping(description, merchant, label, MappingSource.MODEL)
        )
    return out


def system_prompt(labels: Sequence[Label]) -> str:
    lines = "\n".join(f"{x.key}: {x.name} — {x.description}" for x in labels)
    own = next((x.key for x in labels if x.direction == "any"), OWN_MOVE_LABEL.key)
    return SYSTEM_PROMPT.format(own=own, labels=lines)


def categorize(
    items: Sequence[Item],
    labels: Sequence[Label],
    client: ModelClient,
    masker: NarrationMasker | None = None,
) -> CategorizationResult:
    """Categorize distinct descriptions, at most 50 per request.

    With a masker, only masked narrations and label text leave the machine; the reply is matched
    back to the original description by position, so mappings stay keyed on the real narration."""
    distinct = list({i.description: i for i in items if i.description}.values())
    sent, keys = mask_labels(labels, masker)
    to_sent = {path: key for key, path in keys.items()}
    prompt = system_prompt(sent)
    mappings: dict[str, MerchantMapping] = {}
    warnings: list[str] = []
    for batch in _batches(distinct):
        allowed = [{to_sent[x.key] for x in labels_for(i.direction, labels)} for i in batch]
        numbered = "\n".join(
            f"{n}. ({i.direction or 'unknown'}) {masker.narration(i.description) if masker else i.description}"
            for n, i in enumerate(batch, start=1)
        )
        try:
            reply = client.complete(prompt, numbered)
        except Exception as exc:  # unreachable, rate limited, misconfigured: never fail the upload
            log.warning(
                "categorization model call failed: %s", exc
            )  # the API error, never the text
            warnings.append("categorization skipped: the model could not be reached")
            break
        try:
            for description, m in _parse(reply, batch, allowed).items():
                mappings[description] = replace(m, label=keys[m.label])
        except (ValueError, KeyError, TypeError):  # JSONDecodeError is a ValueError
            warnings.append(
                "categorization skipped for a batch: the model reply was not valid JSON"
            )
    unresolved = tuple(i.description for i in distinct if i.description not in mappings)
    if mappings and unresolved:
        warnings.append(f"{len(unresolved)} descriptions left Uncategorized")
    return CategorizationResult(mappings, unresolved, tuple(warnings))


class GenerativeCategorizer:
    """The port over a generative model client (the Claude or OpenAI JSON path)."""

    def __init__(self, client: ModelClient, masker: NarrationMasker | None = None) -> None:
        self.client = client
        self.masker = masker

    def categorize(self, items: Sequence[Item], labels: Sequence[Label]) -> CategorizationResult:
        return categorize(items, labels, self.client, self.masker)
