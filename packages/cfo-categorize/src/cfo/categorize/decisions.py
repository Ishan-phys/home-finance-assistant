"""The Decisions API adapter: OpenAI's typed-answer endpoint as the System-1 categorizer.

Each distinct description is one request with two `choice` questions (spec 4.12.3). The reply is
constrained to the options we give, and carries a probability for each plus a confidence, so
there is no free text to parse and no model-written merchant name to trust.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

from cfo.categorize.categorizer import CategorizationResult
from cfo.categorize.labels import Label, labels_for
from cfo.categorize.merchants import PERSONAL_TRANSFER, clean_merchant
from cfo.categorize.port import Item
from cfo.core.types import MappingSource, MerchantMapping

log = logging.getLogger("cfo.categorize")

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_THRESHOLD = 0.6
DEFAULT_MAX_REQUESTS = 400
UNCLEAR = "unclear"

_CATEGORY_INSTRUCTIONS = (
    "Which category does this Indian bank or credit card statement line belong to? Choose unclear "
    "if the line gives too little to tell."
)


def _category_question(labels: Sequence[Label]) -> dict[str, Any]:
    return {
        "type": "choice",
        "name": "category",
        "instructions": _CATEGORY_INSTRUCTIONS,
        "choices": [
            *[{"value": x.key, "description": f"{x.name}: {x.description}"} for x in labels],
            {"value": UNCLEAR, "description": "Not enough information to tell."},
        ],
    }


_COUNTERPARTY_QUESTION = {
    "type": "choice",
    "name": "counterparty",
    "instructions": "Who is on the other side of this statement line?",
    "choices": [
        {"value": "merchant", "description": "A business, shop, service, or institution."},
        {
            "value": "person",
            "description": "An individual person, for example a friend, family member, or landlord.",
        },
        {
            "value": "own_account",
            "description": "The person's own account or card, such as a card bill payment.",
        },
        {"value": UNCLEAR, "description": "Cannot tell."},
    ],
}


class DecisionsClient(Protocol):
    """The slice of the OpenAI SDK used here: `client.decisions.create(...)`."""

    @property
    def decisions(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class _Outcome:
    mapping: MerchantMapping | None
    input_tokens: int = 0
    aborted: bool = False  # the service is unreachable or refuses us: stop asking


def _input_text(item: Item) -> str:
    way = {"debit": "debit (money out)", "credit": "credit (money in)"}.get(
        item.direction or "", "unknown"
    )
    return (
        "A line from an Indian bank or credit card statement. Personal details were replaced by "
        "tokens such as [PERSON:ab12], which are unknown people or numbers.\n"
        f"Direction: {way}\nNarration: {item.description}"
    )


class DecisionsCategorizer:
    def __init__(
        self,
        client: DecisionsClient,
        *,
        model: str = DEFAULT_MODEL,
        threshold: float = DEFAULT_THRESHOLD,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        workers: int = 8,
    ) -> None:
        self.client = client
        self.model = model
        self.threshold = threshold
        self.max_requests = max_requests
        self.workers = workers

    def categorize(self, items: Sequence[Item], labels: Sequence[Label]) -> CategorizationResult:
        distinct = list({i.description: i for i in items if i.description}.values())
        warnings: list[str] = []
        todo, skipped = distinct[: self.max_requests], distinct[self.max_requests :]
        if skipped:
            warnings.append(
                f"categorization limited to {self.max_requests} descriptions per upload; "
                f"{len(skipped)} left Uncategorized"
            )
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            outcomes = list(pool.map(lambda item: self._one(item, labels), todo))
        mappings = {
            item.description: o.mapping
            for item, o in zip(todo, outcomes, strict=True)
            if o.mapping is not None
        }
        tokens = sum(o.input_tokens for o in outcomes)
        if any(o.aborted for o in outcomes):
            warnings.append("categorization skipped: the model could not be reached")
        unresolved = tuple(i.description for i in distinct if i.description not in mappings)
        if mappings and unresolved and not any(o.aborted for o in outcomes):
            warnings.append(f"{len(unresolved)} descriptions left Uncategorized")
        log.info(
            "decisions: %d requests, %d input tokens, %d labelled", len(todo), tokens, len(mappings)
        )
        return CategorizationResult(mappings, unresolved, tuple(warnings), tokens)

    def _one(self, item: Item, labels: Sequence[Label]) -> _Outcome:
        offered = labels_for(item.direction, labels)
        import openai

        try:
            decision = self.client.decisions.create(
                model=self.model,
                input=_input_text(item),
                questions=[_category_question(offered), _COUNTERPARTY_QUESTION],
            )
        except (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.APIConnectionError,
        ):
            return _Outcome(None, aborted=True)
        except Exception:  # a refusal, a rate limit, a bad reply: this line stays Uncategorized
            return _Outcome(None)
        tokens = int(getattr(getattr(decision, "usage", None), "input_tokens", 0) or 0)
        own_move = next((x.key for x in offered if x.direction == "any"), None)
        return _Outcome(self._mapping(item, decision, {x.key for x in offered}, own_move), tokens)

    def _mapping(
        self, item: Item, decision: Any, offered: set[str], own_move: str | None
    ) -> MerchantMapping | None:
        answers = {a.name: a for a in decision.answers if getattr(a, "type", None) == "choice"}
        category_answer, who = answers.get("category"), answers.get("counterparty")
        if category_answer is None or category_answer.choice == UNCLEAR:
            return None
        if category_answer.confidence < self.threshold:
            return None
        label = str(category_answer.choice)
        counterparty = who.choice if who is not None else None
        if counterparty == "own_account" and own_move is not None:
            label = own_move  # a card bill payment or a move to an own account
        if label not in offered:
            return None
        merchant = (
            PERSONAL_TRANSFER if counterparty == "person" else clean_merchant(item.description)
        )
        return MerchantMapping(
            item.description,
            merchant,
            label,
            MappingSource.MODEL,
            float(category_answer.confidence),
        )


def make_decisions_client(api_key: str | None = None) -> DecisionsClient:
    """An OpenAI client with a short timeout and one retry. Reads OPENAI_API_KEY when no key
    is given."""
    from openai import OpenAI

    return OpenAI(api_key=api_key, timeout=20, max_retries=1)
