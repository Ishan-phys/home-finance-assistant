"""Spec 9.1 acceptance: what actually leaves the machine."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any

import pytest
from cfo.api.app import create_app
from cfo.core.types import AccountType, Direction
from cfo.ingest.retry import retry_categorization
from cfo.ingest.upload import upload_statement
from cfo.ledger.repositories.db import Database
from cfo.ledger.repositories.transactions import JournalRepository
from cfo.ledger.setup import AccountInput, CategoryInput, add_account, add_category
from cfo.testing.api import PersonClient, person_client
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field

TODAY = date(2026, 10, 3)
D = date.fromisoformat

# Private details that must never appear in any outbound request.
ACCOUNT_NAME = "Priya Regalia Savings"
INSTITUTION = "Acme Private Bank"
CATEGORY = "Maid Sunita salary"
PHONE = "9876543210"

STATEMENT = (
    "Statement From : 01/09/2026 To : 30/09/2026\n"
    "Txn Date,Narration,Withdrawals,Deposits,Closing Balance\n"
    f'02/09/2026,UPI/{PHONE}/Rahul,500.00,,"99,500.00"\n'
    '03/09/2026,UPI/Swiggy/Order,250.00,,"99,250.00"\n'
    f'04/09/2026,UPI-ANITA SHARMA-anita.s@okhdfc-HDFC0001234-4012345678-Gift,100.00,,"99,150.00"\n'
).encode()


class Recorder:
    """A categorization model that records every request it is sent."""

    def __init__(self) -> None:
        self.requests: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.requests.append(system + "\n" + user)
        keys = {
            line.split(" — ")[0].split(": ", 1)[1]: line.split(": ", 1)[0]
            for line in system.splitlines()
            if " — " in line and ": " in line
        }
        items = []
        for line in user.splitlines():
            n, text = line.split(". ", 1)
            category = keys["Dining"] if "Swiggy" in text else keys["Shopping"]
            merchant = "Swiggy" if "Swiggy" in text else "Personal transfer"
            items.append({"id": int(n), "merchant": merchant, "category": category})
        return json.dumps({"items": items})


@pytest.fixture
def ledger(database: Database) -> dict[str, Any]:
    with database.transaction() as s:
        acc = add_account(
            s, AccountInput(AccountType.SAVINGS, INSTITUTION, ACCOUNT_NAME), TODAY, "hdfc_bank"
        )
    return {"account": acc.id}


def test_owner_terms_are_applied_at_ingestion_and_again_before_a_retry(
    database: Database, ledger: dict[str, Any]
) -> None:
    api = person_client(database, create_app(db=database, client=Recorder(), clock=lambda: TODAY))
    assert api.put(
        "/privacy/terms", json={"terms": [" Gift ", "gift", "", "Asha Verma"]}
    ).json() == {"terms": ["Gift", "Asha Verma"]}  # trimmed, deduplicated, blanks dropped
    upload_statement(database, ledger["account"], "s.csv", STATEMENT, None, TODAY)  # no model
    with database.transaction() as s:
        stored = "\n".join(t.narration for t in JournalRepository(s).list_all())
    assert "Gift" not in stored and "[PERSON:" in stored  # redacted before it was ever stored
    rec = Recorder()
    retry_categorization(database, rec)
    assert "Gift" not in "\n".join(rec.requests)
    assert api.get("/privacy/terms").json() == {"terms": ["Gift", "Asha Verma"]}


def test_preview_shows_what_is_stored_and_what_a_new_term_would_remove_before_sending(
    database: Database, ledger: dict[str, Any]
) -> None:
    api = person_client(database, create_app(db=database, client=Recorder(), clock=lambda: TODAY))
    upload_statement(database, ledger["account"], "s.csv", STATEMENT, None, TODAY)
    body = api.get("/privacy/preview").json()
    examples = {e["original"]: e["sent"] for e in body["examples"]}
    phone_row = next(o for o in examples if o.startswith("UPI/[PHONE:"))
    assert examples[phone_row] == phone_row  # tokens pass through to the model unchanged
    assert examples["UPI/Swiggy/Order"] == "UPI/Swiggy/Order"
    # a term added after the import is still applied at the model boundary
    api.put("/privacy/terms", json={"terms": ["Swiggy"]})
    after = {e["original"]: e["sent"] for e in api.get("/privacy/preview").json()["examples"]}
    assert after["UPI/Swiggy/Order"] == "UPI/[REDACTED]/Order"
    assert {"real": ACCOUNT_NAME, "alias": "Liquid_Account_1"} in body["aliases"]
    assert {"real": INSTITUTION, "alias": "Institution_1"} in body["aliases"]


class SpyLlm(BaseLlm):
    """Plays the model, records every outbound request, and answers with an alias."""

    model: str = "spy"
    seen: list[Any] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse]:
        self.seen.append(llm_request.model_dump_json())
        last = llm_request.contents[-1]
        results = [p.function_response for p in last.parts or [] if p.function_response]
        if not results:
            question = " ".join(p.text for p in last.parts or [] if p.text).lower()
            name = "get_leaks" if "leak" in question else "get_net_worth"
            call = types.FunctionCall(name=name, args={})
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(function_call=call)])
            )
            return
        r = (results[0].response or {}).get("result", {})
        groups = r.get("groups") or [{}]
        first = (groups[0].get("accounts") or [{"name": "?"}])[0]["name"]
        text = f"Checked {first}. Net worth {r.get('net_worth', {}).get('formatted', 'n/a')}."
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


@pytest.fixture
def chat(database: Database, ledger: dict[str, Any]):  # type: ignore[no-untyped-def]
    upload_statement(database, ledger["account"], "s.csv", STATEMENT, None, TODAY)
    with database.transaction() as s:
        add_category(s, CategoryInput(CATEGORY, Direction.OUT, f"Paid monthly to {CATEGORY}"))
    spy = SpyLlm()
    api = person_client(
        database, create_app(db=database, client=Recorder(), clock=lambda: TODAY, chat_model=spy)
    )
    api.put("/privacy/terms", json={"terms": ["Anita"]})
    return api, spy


def ask(api: PersonClient, message: str) -> list[dict[str, Any]]:
    with api.stream("POST", "/chat", json={"message": message}) as r:
        return [json.loads(x[6:]) for x in r.iter_lines() if x.startswith("data: ")]


def test_chat_request_carries_figures_and_aliases_but_no_private_detail(chat) -> None:  # type: ignore[no-untyped-def]
    api, spy = chat
    events = ask(api, f"What is my net worth? my phone is {PHONE}")
    outbound = "\n".join(spy.seen)
    for private in (ACCOUNT_NAME, INSTITUTION, CATEGORY, PHONE, "Rahul", "Priya", "Sunita"):
        assert private not in outbound, private
    assert "Liquid_Account_1" in outbound  # an alias instead
    assert "formatted" in outbound and "₹" in outbound  # the figures are there
    assert "[REDACTED]" in outbound  # the phone number in the question itself
    # the reply is shown with the real name restored
    text = next(e["text"] for e in events if e["type"] == "text")
    assert ACCOUNT_NAME in text and "Liquid_Account_1" not in text


def test_leak_chat_request_masks_merchants_taken_from_narrations(chat) -> None:  # type: ignore[no-untyped-def]
    api, spy = chat
    ask(api, "Where did my money leak this month?")
    outbound = "\n".join(spy.seen)
    for private in (PHONE, "Rahul", "ANITA", "SHARMA", "anita.s@okhdfc", ACCOUNT_NAME):
        assert private not in outbound, private
    assert "[PHONE:" in outbound or "[PERSON:" in outbound  # tokens, never the details
