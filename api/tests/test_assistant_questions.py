"""The questions an owner asks about their own accounts, and what the model is allowed to see.

The sample ledger has two savings accounts, two cards and two investment accounts, so "which card
spent more" and "which bank account paid out most" have real answers to check.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any

import pytest
from cfo.agent.tools import build_tools
from cfo.api.app import create_app
from cfo.api.sample import load_sample_into
from cfo.ledger.privacy import load_privacy_inputs
from cfo.ledger.repositories.db import Database
from cfo.testing import SeedClient
from cfo.testing.api import PersonClient, person_client
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field

TODAY = date(2026, 10, 3)


@pytest.fixture
def tools(database: Database):  # type: ignore[no-untyped-def]
    load_sample_into(database, database.default_scope, TODAY, SeedClient())
    names = {"Liquid_Account_1": "Sample HDFC Savings", "Credit_Or_Loan_2": "Sample HDFC Card"}
    built = build_tools(database, lambda: TODAY, database.default_scope, lambda t: names.get(t, t))
    return {t.__name__: t for t in built}


def test_which_credit_card_had_more_spending(tools) -> None:  # type: ignore[no-untyped-def]
    result = tools["get_account_activity"](month="2026-09", kind="credit_card")["result"]
    assert {a["account_type"] for a in result["accounts"]} == {"Credit card"}
    assert result["top"]["spending"] == ["Sample HDFC Card"]
    by = {a["account"]: a for a in result["accounts"]}
    assert by["Sample HDFC Card"]["rank_by_spending"] == 1
    assert by["Sample Axis Card"]["rank_by_spending"] == 2
    assert by["Sample HDFC Card"]["spending"]["formatted"] == "₹2,544.50"
    assert result["period"]["in_progress"] is False


def test_which_bank_account_made_more_payments(tools) -> None:  # type: ignore[no-untyped-def]
    result = tools["get_account_activity"](month="2026-09", kind="bank")["result"]
    assert {a["account_type"] for a in result["accounts"]} == {"Savings account"}
    assert result["top"]["payments"] == ["Sample HDFC Savings"]
    first = result["accounts"][0]
    assert first["payments"] >= result["accounts"][1]["payments"]


def test_opening_balances_are_not_payments_and_a_redemption_is_a_transfer(tools) -> None:  # type: ignore[no-untyped-def]
    everyone = tools["get_account_activity"](month="2026-09")["result"]
    funds = next(a for a in everyone["accounts"] if a["account"] == "Sample Groww Mutual Funds")
    assert funds["spending"]["paise"] == 0 and funds["rank_by_spending"] is None
    assert funds["moved_to_own_accounts"]["formatted"] == "₹49,106.00"  # a redemption, in transit
    rows = tools["find_transactions"](limit=25)["result"]["rows"]
    assert not any(r["payee"] == "Opening balance" for r in rows)


def test_find_by_payee_gives_total_months_and_largest_rows(tools) -> None:  # type: ignore[no-untyped-def]
    result = tools["find_transactions"](text="landlord")["result"]
    assert result["count"] == 1 and result["total"]["formatted"] == "₹30,000.00"
    assert result["rows"][0]["category"] == "Housing"
    assert result["by_month"] == [
        {"month": "2026-09", "total": result["total"], "count": 1},
    ]
    assert result["period"] == "all statements"


def test_the_model_names_an_account_by_its_alias_and_it_still_resolves(tools) -> None:  # type: ignore[no-untyped-def]
    result = tools["find_transactions"](account="Credit_Or_Loan_2")["result"]
    assert result["rows"] and {r["account"] for r in result["rows"]} == {"Sample HDFC Card"}
    assert result["filters"]["account"] == "Sample HDFC Card"


@pytest.mark.parametrize(
    ("tool", "args", "message"),
    [
        ("get_account_activity", {"kind": "wallet"}, "kind must be one of"),
        ("get_account_activity", {"month": "September"}, "month must be YYYY-MM"),
        ("get_account_activity", {"month": "2026-09", "start": "2026-09-01"}, "not both"),
        ("get_account_activity", {"start": "2026-09-30", "end": "2026-09-01"}, "not be after"),
        ("get_account_activity", {"start": "yesterday"}, "YYYY-MM-DD"),
        ("find_transactions", {"direction": "sideways"}, "out, in or any"),
        ("find_transactions", {"sort": "size"}, "amount or date"),
        ("find_transactions", {"limit": 0}, "between 1 and 25"),
        ("find_transactions", {"limit": 99}, "between 1 and 25"),
        ("find_transactions", {"account": "Nope Bank"}, "no account matches"),
        ("get_recurring_payments", {"months": 2}, "between 3 and 12"),
    ],
)
def test_bad_requests_come_back_as_an_error_the_model_can_fix(  # type: ignore[no-untyped-def]
    tools, tool: str, args: dict[str, Any], message: str
) -> None:
    result = tools[tool](**args)
    assert message in result["error"] and "result" not in result


def test_an_unknown_account_error_lists_the_accounts_to_choose_from(tools) -> None:  # type: ignore[no-untyped-def]
    error = tools["find_transactions"](account="Nope Bank")["error"]
    assert "Sample HDFC Card" in error and "Sample Axis Card" in error


def test_no_matches_is_an_answer_not_a_failure(tools) -> None:  # type: ignore[no-untyped-def]
    result = tools["find_transactions"](text="zzz-nothing-like-this")["result"]
    assert result["count"] == 0 and result["total"]["paise"] == 0 and result["rows"] == []
    quiet = tools["get_account_activity"](month="2020-01")["result"]
    assert quiet["accounts"] == [] and quiet["top"]["spending"] == []


def test_regular_payments_say_when_there_is_too_little_history(tools) -> None:  # type: ignore[no-untyped-def]
    result = tools["get_recurring_payments"]()["result"]
    assert result["payments"] == [] and "three complete months" in result["note"]


def test_new_tools_on_an_empty_ledger_answer_instead_of_failing(database: Database) -> None:
    empty = {t.__name__: t for t in build_tools(database, lambda: TODAY)}
    for name, args in (
        ("get_account_activity", {}),
        ("find_transactions", {}),
        ("get_recurring_payments", {}),
    ):
        assert "error" not in empty[name](**args), name


def test_every_new_result_is_plain_json_with_no_paths_or_ids(tools) -> None:  # type: ignore[no-untyped-def]
    for name, args in (
        ("get_account_activity", {"month": "2026-09"}),
        ("find_transactions", {"limit": 25}),
        ("get_recurring_payments", {}),
    ):
        result = tools[name](**args)
        text = json.dumps(result)
        assert json.loads(text) == result, name
        for hidden in ("Assets:", "Liabilities:", "Expenses:", "account_id", "transaction_id"):
            assert hidden not in text, (name, hidden)


# what the model is allowed to see ------------------------------------------------------


class SweepLlm(BaseLlm):
    """Calls every tool once, then answers. It sees exactly what a real model would."""

    model: str = "fake-sweep"
    seen: list[Any] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        self.seen.append(llm_request)
        last = llm_request.contents[-1]
        if any(p.function_response for p in last.parts or []):
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="Done.")]))
            return
        calls = [
            ("get_net_worth", {}),
            ("get_spending", {}),
            ("get_trend", {}),
            ("get_account_activity", {"month": "2026-09"}),
            ("find_transactions", {"limit": 25}),
            ("get_recurring_payments", {}),
            ("get_leaks", {}),
            ("get_safe_to_spend", {}),
            ("get_inbox", {}),
        ]
        parts = [types.Part(function_call=types.FunctionCall(name=n, args=a)) for n, a in calls]
        yield LlmResponse(content=types.Content(role="model", parts=parts))


@pytest.fixture
def sweep(database: Database):  # type: ignore[no-untyped-def]
    load_sample_into(database, database.default_scope, TODAY, SeedClient())
    fake = SweepLlm()
    app = create_app(db=database, client=SeedClient(), clock=lambda: TODAY, chat_model=fake)
    return person_client(database, app), fake


def ask(client: PersonClient, message: str) -> list[dict[str, Any]]:
    with client.stream("POST", "/chat", json={"message": message, "session_id": None}) as r:
        assert r.status_code == 200
        return [json.loads(x[6:]) for x in r.iter_lines() if x.startswith("data: ")]


def test_nothing_private_reaches_the_model(sweep, database: Database) -> None:  # type: ignore[no-untyped-def]
    """Every request, the system instruction included, after all nine tools have answered and
    the owner has typed their own name and a real account name into the question."""
    client, fake = sweep
    events = ask(client, "Did Zelda Voss spend more on Sample HDFC Card or Sample Axis Card?")
    assert {e["name"] for e in events if e["type"] == "tool"} == set(
        t.__name__ for t in build_tools(database, lambda: TODAY)
    )
    with database.transaction() as s:
        private = load_privacy_inputs(s)
    secrets = list(private["terms"])  # type: ignore[call-overload]
    for _key, name, _family, institution, reference in private["accounts"]:  # type: ignore[misc]
        secrets += [name, institution, reference]
    secrets = [x for x in secrets if x]
    assert len(secrets) >= 8  # the owner's name and every account and institution

    sent = []
    for request in fake.seen:
        sent.append(json.dumps([c.model_dump(mode="json") for c in request.contents]))
        sent.append(str(request.config.system_instruction))
    blob = "\n".join(sent).lower()
    assert "credit_or_loan_" in blob and "liquid_account_" in blob  # stand-ins are there
    for secret in secrets:
        assert secret.lower() not in blob, f"{secret!r} reached the model"


def test_the_owner_reads_real_names_even_though_the_model_never_saw_them(  # type: ignore[no-untyped-def]
    database: Database,
) -> None:
    load_sample_into(database, database.default_scope, TODAY, SeedClient())

    class Echo(SweepLlm):
        async def generate_content_async(  # type: ignore[override]
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse]:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text="Most on Credit_Or_Loan_2, see [x](https://evil.example/?q=1)"
                        )
                    ],
                )
            )

    app = create_app(db=database, client=SeedClient(), clock=lambda: TODAY, chat_model=Echo())
    reply = next(e for e in ask(person_client(database, app), "hi") if e["type"] == "text")["text"]
    assert reply.startswith("Most on Sample ") and "Card" in reply  # a real name came back
    assert "evil.example" not in reply and "](" not in reply  # and the link did not
