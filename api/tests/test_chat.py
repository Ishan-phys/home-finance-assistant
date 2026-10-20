"""Chat with a fake model: the agent's figures come from tool results, and the local tool
path is fast. The fake plays the model's part: it picks a tool from the question, then writes
the reply from the tool result it is handed, so a wrong figure could only come from the tools."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any

import pytest
from cfo.agent.service import INSTRUCTION
from cfo.agent.tools import build_tools
from cfo.api.app import create_app
from cfo.api.sample import load_sample_into
from cfo.ledger import reports
from cfo.ledger.repositories.db import Database
from cfo.testing import SeedClient
from cfo.testing.api import PersonClient, person_client
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field

TODAY = date(2026, 10, 3)


class FakeLlm(BaseLlm):
    model: str = "fake-cfo"
    seen: list[Any] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        self.seen.append(llm_request)
        last = llm_request.contents[-1]
        results = [p.function_response for p in last.parts or [] if p.function_response]
        if not results:
            question = " ".join(p.text for p in last.parts or [] if p.text).lower()
            name = "get_leaks" if "leak" in question else "get_safe_to_spend"
            call = types.FunctionCall(name=name, args={})
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(function_call=call)])
            )
            return
        r = (results[0].response or {})["result"]
        if results[0].name == "get_safe_to_spend":
            text = (
                f"You can spend {r['amount']['formatted']}: {r['liquid']['formatted']} in cash and "
                f"savings, less {r['owed_on_cards']['formatted']} owed on cards."
            )
        else:
            text = f"In {r['month']} {len(r['rows'])} payees grew. Reason: {r['reason']}."
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


@pytest.fixture
def chat_env(database: Database):  # type: ignore[no-untyped-def]
    load_sample_into(database, database.default_scope, TODAY, SeedClient())
    fake = FakeLlm()
    app = create_app(db=database, client=SeedClient(), clock=lambda: TODAY, chat_model=fake)
    return person_client(database, app), fake


def ask(client: PersonClient, message: str, session_id: str | None = None) -> list[dict[str, Any]]:
    with client.stream("POST", "/chat", json={"message": message, "session_id": session_id}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        return [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]


def test_afford_question_calls_safe_to_spend_and_quotes_the_result(
    chat_env, database: Database
) -> None:
    client, _ = chat_env
    events = ask(client, "Can I afford a ₹40,000 trip to Goa next month?")
    tool = next(e for e in events if e["type"] == "tool")
    assert tool["name"] == "get_safe_to_spend"
    with database.transaction() as s:
        truth = reports.safe_to_spend_report(reports.load(s, TODAY))
    text = next(e["text"] for e in events if e["type"] == "text")
    for figure in (truth["amount"], truth["liquid"], truth["owed_on_cards"]):
        assert figure["formatted"] in text  # quoted from the tool result, not computed
    assert events[-1] == {"type": "done"}


def test_leak_question_calls_get_leaks_and_uses_its_result(chat_env, database: Database) -> None:
    client, _ = chat_env
    events = ask(client, "Where did my money leak this month?")
    assert next(e for e in events if e["type"] == "tool")["name"] == "get_leaks"
    with database.transaction() as s:
        truth = reports.leaks_report(reports.load(s, TODAY))
    text = next(e["text"] for e in events if e["type"] == "text")
    assert truth["month"] in text and str(truth["reason"]) in text  # a partial month is stated


def test_session_history_is_kept_for_the_process(chat_env) -> None:
    client, fake = chat_env
    sid = next(e for e in ask(client, "leak?") if e["type"] == "session")["session_id"]
    ask(client, "and the goa trip?", sid)
    assert len(fake.seen) == 4  # two turns, each a tool call then an answer
    second_turn_first_request = fake.seen[2]
    assert len(second_turn_first_request.contents) > 1  # the earlier turn is in the context


def test_instruction_carries_the_figure_and_coverage_rules() -> None:
    text = INSTRUCTION.lower()
    for rule in (
        "call a tool before stating any figure",
        "never convert paise",
        "credit card balances and loans reduce it",
        "name the statement upload",
    ):
        assert rule in " ".join(text.split()), rule


def test_local_tool_path_is_under_300ms(database: Database) -> None:
    load_sample_into(database, database.default_scope, TODAY, SeedClient())
    tools = build_tools(database, lambda: TODAY)
    for tool in tools:  # warm the connection pool once, then time the real path
        tool()
    for tool in tools:
        start = time.perf_counter()
        result = tool()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.3, f"{tool.__name__} took {elapsed:.3f}s"
        assert "error" not in result


def test_tool_arguments_are_validated_not_trusted(database: Database) -> None:
    tools = {t.__name__: t for t in build_tools(database, lambda: TODAY)}
    assert "error" in tools["get_spending"](month="October")
    assert "error" in tools["get_net_worth"](as_of="not-a-date")
    empty = tools["get_net_worth"]()
    assert empty["result"]["net_worth"]["paise"] == 0  # an empty ledger answers, it does not fail


def test_every_tool_result_is_plain_json(database: Database) -> None:
    """A model client serializes tool results with the standard library. A UUID, a tuple of
    them, or a date would break the real model while a fake never notices."""
    load_sample_into(database, database.default_scope, TODAY, SeedClient())
    for tool in build_tools(database, lambda: TODAY, database.default_scope):
        result = tool()
        assert "path" not in json.dumps(result)  # account paths never reach the model
        assert json.loads(json.dumps(result)) == result, tool.__name__
