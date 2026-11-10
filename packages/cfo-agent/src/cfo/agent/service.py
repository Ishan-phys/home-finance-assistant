"""One Google ADK agent over the six tools (spec 4.6, design §5.12).

History lives in the ADK in-memory session service, for the life of the API process only.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import date
from typing import Any

from cfo.agent.masking import build_masker
from cfo.agent.prompt import build_instruction
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

INSTRUCTION = build_instruction()  # every tool, no date: what the tests and docs read

# A reply never needs a link, an image or markup, and each is a way for text hidden in a bank
# narration to carry the owner's data out (an image URL is fetched by the browser). They are
# dropped here, and the browser refuses images again.
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HTML = re.compile(r"</?[A-Za-z][^>]*>")
_URL = re.compile(r"\bhttps?://\S+", re.IGNORECASE)


def scrub_reply(text: str) -> str:
    """The reply with images, links, HTML tags and web addresses removed (link text is kept)."""
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _HTML.sub("", text)
    return _URL.sub("", text)


def _instruction(clock: Callable[[], date], tool_names: list[str]) -> Callable[[Any], str]:
    """The instruction for these tools with today's date, so "this month" and "last month" mean
    something. A function, not a string: ADK would read braces in a string as variables."""

    def provide(_: Any) -> str:
        return build_instruction(clock(), tool_names)

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
        self.tools = build_tools(db, clock, scope, self._unalias)
        self.agent = LlmAgent(
            name="cfo",
            model=model,
            instruction=_instruction(clock, [t.__name__ for t in self.tools]),
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

    def _unalias(self, text: str) -> str:
        """A name as the model saw it (an alias), as the ledger knows it."""
        return self._masker().unalias(text)

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
                part.text = masker.unalias(scrub_reply(part.text))
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
