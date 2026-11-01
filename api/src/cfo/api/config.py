"""Environment-driven settings. Keys are read by the SDKs from OPENAI_API_KEY and ANTHROPIC_API_KEY."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    categorizer: str  # auto | openai_decisions | anthropic | none
    decisions_model: str
    decisions_threshold: float
    categorization_model: str  # the generative fallback
    chat_model: str  # empty means the provider's default
    allowed_hosts: tuple[str, ...] = ()  # empty means this machine and the web service

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            database_url=env("DATABASE_URL")
            or "postgresql+psycopg://cfo:cfo-local-dev@localhost:5432/cfo",
            categorizer=(env("CATEGORIZER") or "auto").lower(),
            decisions_model=env("DECISIONS_MODEL") or "gpt-6-luna",
            decisions_threshold=float(env("DECISIONS_THRESHOLD") or 0.6),
            categorization_model=env("CATEGORIZATION_MODEL") or "claude-haiku-4-5-20251001",
            chat_model=env("CHAT_MODEL") or "",
            allowed_hosts=tuple(
                h.strip() for h in (env("ALLOWED_HOSTS") or "").split(",") if h.strip()
            ),
        )
