"""The Decisions adapter against the real SDK's types: requests are checked against the SDK's own
parameter definitions, and replies are built as the SDK's own `Decision` models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx2
import openai
import pytest
from cfo.categorize.decisions import DEFAULT_MODEL, DecisionsCategorizer
from cfo.categorize.port import OWN_MOVE_LABEL, Categorizer, Item, Label, as_categorizer
from cfo.core.chart import IN_TRANSIT
from cfo.core.types import MappingSource
from openai.types import Decision, decision_create_params
from pydantic import TypeAdapter


def choice(name: str, value: str, confidence: float, options: Sequence[str]) -> dict[str, Any]:
    rest = (1 - confidence) / max(len(options) - 1, 1)
    return {
        "type": "choice",
        "name": name,
        "choice": value,
        "confidence": confidence,
        "probabilities": [
            {"value": o, "probability": confidence if o == value else rest} for o in options
        ],
    }


DINING = Label("Expenses:Food:Dining", "Dining", "Restaurants, cafés, food delivery", "debit")
SHOPPING = Label("Expenses:Shopping", "Shopping", "Clothes, electronics, online shopping", "debit")
HOUSING = Label("Expenses:Housing", "Housing", "Rent, maintenance", "debit")
SALARY = Label("Income:Salary", "Salary", "Pay from your employer", "credit")
LABELS = [DINING, SHOPPING, HOUSING, SALARY, OWN_MOVE_LABEL]
CATEGORIES = [x.key for x in LABELS] + ["unclear"]
WHO = ["merchant", "person", "own_account", "unclear"]


def decision(
    category: str, conf: float = 0.93, who: str = "merchant", tokens: int = 120
) -> Decision:
    return Decision.model_validate(
        {
            "answers": [
                choice("category", category, conf, CATEGORIES),
                choice("counterparty", who, 0.9, WHO),
            ],
            "model": "gpt-6-luna",
            "usage": {
                "input_tokens": tokens,
                "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
                "output_tokens": 0,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": tokens,
            },
        }
    )


class FakeDecisions:
    def __init__(self, reply: Any) -> None:
        self.reply, self.calls = reply, []

    def create(self, **kwargs: Any) -> Decision:
        self.calls.append(kwargs)
        result = self.reply(kwargs) if callable(self.reply) else self.reply
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[no-any-return]


class FakeClient:
    def __init__(self, reply: Any) -> None:
        self.decisions = FakeDecisions(reply)


def run(reply: Any, descriptions: list[str], labels: Sequence[Label] = LABELS, **kw: Any):  # type: ignore[no-untyped-def]
    client = FakeClient(reply)
    categorizer = DecisionsCategorizer(client, **kw)
    return categorizer.categorize(
        [Item(d, "debit") for d in descriptions], labels
    ), client.decisions


def test_the_sdk_has_the_decisions_resource() -> None:
    assert hasattr(openai.OpenAI(api_key="sk-test"), "decisions")


def test_requests_match_the_sdks_own_parameter_types() -> None:
    _, fake = run(decision(DINING.key), ["UPI-SWIGGY-[VPA:ab12]-ICIC[ID:cd34]"])
    call = fake.calls[0]
    assert call["model"] == DEFAULT_MODEL
    TypeAdapter(list[decision_create_params.Question]).validate_python(call["questions"])
    assert [q["name"] for q in call["questions"]] == ["category", "counterparty"]
    choices = call["questions"][0]["choices"]
    # a debit is offered the money-out categories and own-account moves, not salary
    assert [c["value"] for c in choices] == [
        DINING.key,
        SHOPPING.key,
        HOUSING.key,
        IN_TRANSIT,
        "unclear",
    ]
    assert choices[0]["description"] == "Dining: Restaurants, cafés, food delivery"
    assert "Direction: debit (money out)" in call["input"] and "UPI-SWIGGY" in call["input"]


def test_a_confident_answer_becomes_a_mapping_with_a_locally_derived_merchant() -> None:
    result, _ = run(decision(DINING.key, 0.93), ["UPI-SWIGGY-[VPA:ab12]-ICIC[ID:cd34]-1-Order"])
    m = result.mappings["UPI-SWIGGY-[VPA:ab12]-ICIC[ID:cd34]-1-Order"]
    assert (m.label, m.clean_merchant) == (DINING.key, "Swiggy")
    assert m.source is MappingSource.MODEL and m.confidence == pytest.approx(0.93)
    assert result.unresolved == () and result.input_tokens == 120


@pytest.mark.parametrize(
    ("label", "confidence"),
    [
        ("unclear", 0.95),  # the model says it cannot tell
        (DINING.key, 0.59),  # below the threshold: a shaky guess never enters a metric
        ("Expenses:Entertainment", 0.95),  # not one of the ledger's categories
        (SALARY.key, 0.95),  # an income category for money going out
    ],
)
def test_only_offered_confident_answers_enter_the_ledger(label: str, confidence: float) -> None:
    result, _ = run(decision(label, confidence), ["SOMETHING"])
    assert result.mappings == {} and result.unresolved == ("SOMETHING",)


def test_threshold_boundary_and_a_person_counterparty() -> None:
    at, _ = run(decision(SHOPPING.key, 0.6), ["A"])
    assert "A" in at.mappings
    person, _ = run(decision(SHOPPING.key, 0.9, who="person"), ["UPI/[PHONE:ab12]/[PERSON:cd34]"])
    assert person.mappings["UPI/[PHONE:ab12]/[PERSON:cd34]"].clean_merchant == "Personal transfer"
    strict, _ = run(decision(SHOPPING.key, 0.7), ["A"], threshold=0.8)
    assert strict.mappings == {}


def test_an_own_account_counterparty_is_money_in_transit() -> None:
    result, _ = run(decision(SHOPPING.key, 0.9, who="own_account"), ["CC BILLPAY"])
    assert result.mappings["CC BILLPAY"].label == IN_TRANSIT


def test_credits_are_offered_income_and_refunds_but_debits_no_income() -> None:
    client = FakeClient(decision(SALARY.key))
    DecisionsCategorizer(client).categorize([Item("NEFT CR SALARY", "credit")], LABELS)
    offered = [c["value"] for c in client.decisions.calls[0]["questions"][0]["choices"]]
    assert SALARY.key in offered and DINING.key in offered  # a refund credits a spending category


def test_custom_label_text_is_masked() -> None:
    class Masker:
        def narration(self, text: str) -> str:
            return text.replace("Tara Nair", "[PERSON:aa11]")

    label = Label("Expenses:Tara-Rent", "Tara Nair rent", "rent paid to Tara Nair", "debit")
    client = FakeClient(lambda call: decision(call["questions"][0]["choices"][0]["value"]))
    wrapped = as_categorizer(DecisionsCategorizer(client), Masker())
    assert wrapped is not None
    result = wrapped.categorize([Item("UPI-Tara Nair-RENT", "debit")], [label])
    sent = str(client.decisions.calls[0]).lower()
    assert "tara" not in sent  # not in the narration, the name, the description or the key
    assert result.mappings["UPI-Tara Nair-RENT"].label == label.key  # keyed on the stored text


def test_a_refusal_leaves_that_line_alone() -> None:
    refusal = Decision.model_validate(
        {
            "answers": [{"type": "refusal", "name": "category"}],
            "model": "gpt-6-luna",
            "usage": decision(DINING.key).usage.model_dump(),
        }
    )
    result, _ = run(refusal, ["A"])
    assert result.mappings == {} and result.unresolved == ("A",)


def test_an_unreachable_service_aborts_with_one_warning_and_never_raises() -> None:
    request = httpx2.Request("POST", "https://api.openai.com/v1/decisions")
    down = openai.APIConnectionError(request=request)
    result, _ = run(down, ["A", "B", "C"])
    assert result.mappings == {} and set(result.unresolved) == {"A", "B", "C"}
    assert result.warnings == ("categorization skipped: the model could not be reached",)
    denied = openai.AuthenticationError(
        "bad key", response=httpx2.Response(401, request=request), body=None
    )
    assert "could not be reached" in run(denied, ["A"])[0].warnings[0]


def test_one_bad_reply_does_not_stop_the_others() -> None:
    def reply(call: dict[str, Any]) -> Any:
        return RuntimeError("boom") if "BAD" in call["input"] else decision(DINING.key)

    result, _ = run(reply, ["GOOD1", "BAD", "GOOD2"])
    assert set(result.mappings) == {"GOOD1", "GOOD2"} and result.unresolved == ("BAD",)
    assert result.warnings == ("1 descriptions left Uncategorized",)


def test_the_request_ceiling_and_dedup() -> None:
    result, fake = run(
        decision(DINING.key), [f"D{i}" for i in range(5)] + ["D0", "D1"], max_requests=3
    )
    assert len(fake.calls) == 3  # distinct descriptions only, capped
    assert len(result.mappings) == 3 and len(result.unresolved) == 2
    assert any("limited to 3" in w for w in result.warnings)


def test_it_satisfies_the_port_and_a_generative_client_can_stand_in() -> None:
    assert isinstance(DecisionsCategorizer(FakeClient(decision(DINING.key))), Categorizer)

    class Generative:
        def complete(self, system: str, user: str) -> str:
            return (
                '{"items": [{"id": 1, "merchant": "Swiggy", "category": "Expenses:Food:Dining"}]}'
            )

    wrapped = as_categorizer(Generative())
    assert isinstance(wrapped, Categorizer)
    got = wrapped.categorize([Item("SWIGGY ORDER", "debit")], LABELS).mappings["SWIGGY ORDER"]
    assert got.label == DINING.key
    assert as_categorizer(None) is None
