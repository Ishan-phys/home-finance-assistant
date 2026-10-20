"""Server-sent events endpoint for chat."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import date

from cfo.agent.service import ChatService
from cfo.api.deps import ScopeDep
from cfo.core.ids import Id
from cfo.core.types import Scope
from cfo.ledger.repositories.db import Database
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from google.adk.models.base_llm import BaseLlm
from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class ChatRegistry:
    """One chat service per ledger: its tools read only that ledger, and its in-memory sessions
    are never shared between people."""

    def __init__(self, db: Database, clock: Callable[[], date], model: BaseLlm | str) -> None:
        self.db, self.clock, self.model = db, clock, model
        self._services: dict[frozenset[Id], ChatService] = {}

    def for_scope(self, scope: Scope) -> ChatService:
        if scope.ledger_ids not in self._services:
            self._services[scope.ledger_ids] = ChatService(self.db, self.clock, self.model, scope)
        return self._services[scope.ledger_ids]


def add_chat_routes(router: APIRouter, chats: ChatRegistry) -> None:
    @router.post("/chat")
    async def chat_endpoint(body: ChatIn, scope: ScopeDep) -> StreamingResponse:
        chat = chats.for_scope(scope)

        async def events() -> AsyncIterator[str]:
            try:
                async for item in chat.stream(body.message, body.session_id):
                    yield f"data: {json.dumps(item)}\n\n"
            except Exception:  # the stream is already open; report in-band, never leak details
                yield f"data: {json.dumps({'type': 'error', 'message': 'the assistant could not answer'})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
