"""One Google ADK agent over the six tools (spec 4.6, design §5.12).

History lives in the ADK in-memory session service, for the life of the API process only.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import date
from typing import Any

from cfo.agent.masking import build_masker
from cfo.agent.tools import build_tools
from cfo.core.types import Scope
from cfo.ledger.repositories.db import Database
from cfo.redact.masker import Masker
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

APP_NAME = "ai_cfo"
USER_ID = "owner"

INSTRUCTION = """You are the owner's personal CFO: a sharp, warm adviser who has read their books
and tells them what the numbers mean. Python has already computed every figure; your job is to
find what matters in them and say it plainly. You never calculate, estimate, or round a figure.

FIGURES
1. Call a tool before stating any figure. Quote amounts, percents and directions exactly as the
   tool gives them ("formatted", "percent", "direction"); never convert paise yourself.
2. Never add, subtract, divide or compare numbers yourself, not even to say "about double". If a
   comparison matters and no tool field states it, say what the tool does show and leave the
   gap unfilled. Never invent a figure, a date, a merchant or a cause.
3. Use names exactly as the tools give them, including any alias that looks odd.

HOW TO WORK
4. Gather before you answer. For a broad question ("how am I doing?", "give me an overview",
   "any advice?") call several tools in one go: get_trend, get_spending, get_safe_to_spend,
   get_net_worth and get_inbox. For a narrow question call the one tool that answers it, and add
   get_trend when the answer needs a comparison.
5. Look for what is notable, not for everything: the biggest category and its share of
   spending, what moved against last month or the average (get_trend), the savings rate against
   the usual, a payee that grew (get_leaks), money owed on cards against cash, a shrinking or
   growing net worth, and anything that will need cash soon. Lead with the one or two findings
   that most change what the owner should do.
6. Explain why, honestly. Tie a change to the category or payee the tools show behind it. If
   the data only suggests a cause, say "this looks like" or "it may be"; do not state it as fact.
   A swing of several hundred percent usually means the earlier month held little data (such as
   the first statement uploaded); say that instead of presenting it as a real surge.

DATA QUALITY
7. A month that is not complete is partial: never present it as a total or compare it with full
   months as if it were one. Say it is the month so far.
8. When get_inbox shows a gap, an unpaired movement or uncategorized rows that affect the
   answer, say so once, briefly, and name the statement upload or fix that would resolve it.
   Do not bury the answer under caveats, and never refuse because data is incomplete.
9. Net worth includes what is owed: credit card balances and loans reduce it. Investments,
   deposits, property and gold are never spendable. For "can I afford" questions use
   get_safe_to_spend and explain what was subtracted.

HOW TO ANSWER
10. Open with the answer in one or two sentences. Then give the evidence as a short bulleted
    list with the key figure in **bold**. Then, only if it is useful, one concrete next step the
    owner can take (a category to review, a bill to plan for, an upload to make). Use a small
    Markdown table only to compare months or categories, with at most six rows.
11. Keep it under about 150 words unless the owner asks for detail. Plain English for someone
    who is not an accountant. No emojis, no headings, no code blocks, no filler such as "Great
    question". Ask at most one follow-up question, and only if it would change your advice.
12. You can describe habits and trade-offs, but you give no tax, legal or investment-product
    advice and recommend no specific security. You cannot place trades, move money, change the
    ledger or hold bank credentials; point to the Transactions and Rules pages for fixes.
"""


def _instruction(clock: Callable[[], date]) -> Callable[[Any], str]:
    """The instruction with today's date, so "this month" and "last month" mean something.
    A function, not a string: ADK would read the braces in a string as template variables."""

    def provide(_: Any) -> str:
        today = clock()
        return f"{INSTRUCTION}\nToday is {today.day} {today.strftime('%B %Y')}.\n"

    return provide


def _mask_content(content: types.Content, masker: Masker) -> types.Content:
    """A masked copy of one message. The session history itself is never altered."""
    parts: list[types.Part] = []
    for part in content.parts or []:
        copy = part.model_copy(deep=True)
        if copy.text:
            copy.text = masker.text(copy.text)
        if copy.function_call is not None and copy.function_call.args:
            copy.function_call.args = masker.payload(dict(copy.function_call.args))
        if copy.function_response is not None and copy.function_response.response:
            copy.function_response.response = masker.payload(dict(copy.function_response.response))
        parts.append(copy)
    return types.Content(role=content.role, parts=parts)


class ChatService:
    def __init__(
        self,
        db: Database,
        clock: Callable[[], date],
        model: BaseLlm | str,
        scope: Scope | None = None,
    ) -> None:
        self.db = db
        self.scope = scope
        self.tools = build_tools(db, clock, scope)
        self.agent = LlmAgent(
            name="cfo",
            model=model,
            instruction=_instruction(clock),
            tools=list(self.tools),
            before_model_callback=self._mask_request,
            after_model_callback=self._unmask_response,
        )
        self.runner = Runner(
            app_name=APP_NAME,
            agent=self.agent,
            session_service=InMemorySessionService(),
            auto_create_session=True,
        )

    def _masker(self) -> Masker:
        with self.db.transaction(self.scope) as s:
            return build_masker(s)

    def _mask_request(self, callback_context: Any, llm_request: Any) -> None:
        """Mask every message just before it leaves for the model (spec 9.1): real account and
        rule names become aliases, narrations lose names, handles and long numbers. Amounts
        stay numeric. Returning None lets the call proceed with the masked request."""
        masker = self._masker()
        llm_request.contents = [_mask_content(c, masker) for c in llm_request.contents]
        return None

    def _unmask_response(self, callback_context: Any, llm_response: Any) -> Any:
        """Put real names back into the reply before the browser renders it."""
        content = llm_response.content
        if content is None or not content.parts or not any(p.text for p in content.parts):
            return None
        masker = self._masker()
        reply = llm_response.model_copy(deep=True)
        for part in reply.content.parts:
            if part.text:
                part.text = masker.unalias(part.text)
        return reply

    async def stream(self, message: str, session_id: str | None) -> AsyncIterator[dict[str, Any]]:
        """Yield events: the session id, each tool call, the reply text, then done."""
        sid = session_id or uuid.uuid4().hex
        yield {"type": "session", "session_id": sid}
        content = types.Content(role="user", parts=[types.Part(text=message)])
        async for event in self.runner.run_async(
            user_id=USER_ID, session_id=sid, new_message=content
        ):
            if event.content is None or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.function_call is not None:
                    yield {
                        "type": "tool",
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args or {}),
                    }
                elif part.text and event.author != "user" and not event.partial:
                    yield {"type": "text", "text": part.text}
        yield {"type": "done"}
