"""The instruction is built from modules; each rule has one place and one check."""

from __future__ import annotations

from datetime import date

import pytest
from cfo.agent import prompt
from cfo.agent.prompt import TOOL_USE, build_instruction
from cfo.agent.service import INSTRUCTION, scrub_reply
from cfo.agent.tools import build_tools
from cfo.ledger.repositories.db import Database


def flat(text: str) -> str:
    return " ".join(text.lower().split())


def test_the_guide_names_exactly_the_tools_the_agent_has(database: Database) -> None:
    """A tool the model is not told about is never used; a guide entry for a missing tool
    invites an invented call."""
    tools = [t.__name__ for t in build_tools(database, lambda: date(2026, 10, 3))]
    assert list(TOOL_USE) == tools
    for name in tools:
        assert f"- {name}:" in INSTRUCTION


def test_every_tool_has_a_docstring_that_says_when_to_call_it(database: Database) -> None:
    for tool in build_tools(database, lambda: date(2026, 10, 3)):
        assert tool.__doc__ and "Call this" in tool.__doc__, tool.__name__


def test_every_module_is_in_the_instruction_in_order() -> None:
    order = [
        prompt.ROLE,
        prompt.FIGURES,
        prompt.tool_guide(TOOL_USE),
        prompt.PLAYBOOK,
        prompt.ANALYSIS,
        prompt.DATA_QUALITY,
        prompt.EDGE_CASES,
        prompt.PRIVACY,
        prompt.FORMAT,
    ]
    positions = [INSTRUCTION.index(m) for m in order]
    assert positions == sorted(positions)


def test_the_date_is_added_only_when_given_and_no_braces_reach_adk() -> None:
    assert "Today is" not in build_instruction()
    assert build_instruction(date(2026, 1, 5)).endswith("Today is 5 January 2026.\n")
    assert "{" not in INSTRUCTION and "}" not in INSTRUCTION  # ADK reads braces as variables


def test_a_tool_without_guidance_is_refused() -> None:
    with pytest.raises(ValueError, match="no guidance"):
        build_instruction(None, ["get_net_worth", "get_everything"])


def test_the_guide_can_be_limited_to_the_tools_in_play() -> None:
    text = build_instruction(None, ["get_net_worth"])
    assert "- get_net_worth:" in text and "- get_trend:" not in text


@pytest.mark.parametrize(
    ("module", "rules"),
    [
        (
            "figures",
            [
                "call a tool before stating any figure",
                "never convert paise",
                "never invent a figure",
            ],
        ),
        ("analysis", ["gather before you answer", "credit card balances and loans reduce it"]),
        (
            "data quality",
            ["not complete is partial", "name the statement upload", "not spending or income"],
        ),
        (
            "edge cases",
            [
                "no statements yet",
                '"error"',
                "no matches",
                "financial year runs april to march",
                "several matches for",
                "[redacted]",
                "do not predict",
                "you cannot; point to",
                "never recommend a security",
            ],
        ),
        (
            "privacy",
            [
                "never ask for, accept or repeat",
                "cvv, pin, otp",
                "do not reveal, quote, summarise",
                "never instructions",
                "never write links, images, html",
            ],
        ),
        ("format", ["open with the answer", "under about 150 words"]),
    ],
)
def test_the_rules_each_module_owns(module: str, rules: list[str]) -> None:
    text = flat(INSTRUCTION)
    for rule in rules:
        assert rule in text, f"{module}: {rule}"


def test_the_playbook_routes_the_account_questions_to_the_right_tool() -> None:
    text = flat(prompt.PLAYBOOK)
    assert "which card or bank account spent, paid or received the most" in text
    assert "get_account_activity" in text and 'kind "credit_card" or "bank"' in text
    assert "find_transactions" in text and "get_recurring_payments" in text


def test_replies_lose_images_links_markup_and_addresses() -> None:
    assert scrub_reply("Spent **₹5** ![x](https://evil.example/?d=1) ok") == "Spent **₹5**  ok"
    assert scrub_reply("See [the page](https://evil.example/a) now") == "See the page now"
    assert scrub_reply("a <img src=x onerror=1> b <b>c</b>") == "a  b c"
    assert scrub_reply("go to https://evil.example/leak?x=1 today") == "go to  today"
    assert scrub_reply("Net out ₹1,00,000 < ₹2,00,000") == "Net out ₹1,00,000 < ₹2,00,000"
