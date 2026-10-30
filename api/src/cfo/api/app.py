"""FastAPI application: request validation and response mapping over the services."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from cfo.api import errors
from cfo.api.chat import ChatRegistry
from cfo.api.config import Settings
from cfo.categorize.categorizer import AnthropicClient, ModelClient
from cfo.categorize.decisions import DecisionsCategorizer, make_decisions_client
from cfo.categorize.port import Categorizer
from cfo.core.dates import today_ist
from cfo.ledger.repositories.db import Database
from cfo.vault import Vault, load_vault
from fastapi import FastAPI
from google.adk.models.anthropic_llm import AnthropicLlm
from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import LiteLlm


@dataclass(slots=True)
class Deps:
    db: Database
    client: Categorizer | ModelClient | None
    clock: Callable[[], date]
    settings: Settings
    vault: Vault | None = None  # seals original narrations; None keeps none


class ProviderConfigError(RuntimeError):
    """The model-provider keys in the environment cannot be used as given."""


def provider_from_env() -> str | None:
    """`openai` or `anthropic`, by whichever API key is set; None when neither is. One key runs
    both chat and categorization. Both at once is ambiguous, so it is refused rather than guessed."""
    openai_key, anthropic_key = (
        os.environ.get("OPENAI_API_KEY"),
        os.environ.get("ANTHROPIC_API_KEY"),
    )
    if openai_key and anthropic_key:
        raise ProviderConfigError(
            "both OPENAI_API_KEY and ANTHROPIC_API_KEY are set; set only one in .env"
        )
    return "openai" if openai_key else "anthropic" if anthropic_key else None


def build_categorizer(cfg: Settings) -> Categorizer | ModelClient | None:
    """The System-1 categorizer for the provider whose key is set; with no key, nothing is
    categorized (rows stay Uncategorized, with a warning). `CATEGORIZER=none` turns it off."""
    if cfg.categorizer == "none":
        return None
    provider = provider_from_env()
    if provider == "openai":
        return DecisionsCategorizer(
            make_decisions_client(), model=cfg.decisions_model, threshold=cfg.decisions_threshold
        )
    if provider == "anthropic":
        return AnthropicClient(cfg.categorization_model)
    return None


DEFAULT_CHAT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-5.5"}


def build_chat_model(cfg: Settings) -> BaseLlm:
    """The chat model for the provider whose key is set. With no key, chat is built for Claude so
    the dock reports a clear error."""
    provider = provider_from_env() or "anthropic"
    model = cfg.chat_model or DEFAULT_CHAT_MODELS[provider]
    if provider == "openai":
        return LiteLlm(model=f"openai/{model}")
    return AnthropicLlm(model=model)


def create_app(
    db: Database | None = None,
    client: Categorizer | ModelClient | None = None,
    clock: Callable[[], date] = today_ist,
    settings: Settings | None = None,
    chat_model: BaseLlm | str | None = None,
    vault: Vault | None = None,
) -> FastAPI:
    """Build the app. The defaults read the environment; tests pass their own pieces."""
    from cfo.api.routes import build_router  # noqa: PLC0415

    cfg = settings or Settings.from_env()
    deps = Deps(
        db=db or Database(cfg.database_url),
        client=client or build_categorizer(cfg),
        clock=clock,
        settings=cfg,
        vault=vault or load_vault(os.environ),
    )
    app = FastAPI(title="AI CFO", version="0.1.0")
    errors.install(app)
    model = chat_model or build_chat_model(cfg)
    app.include_router(build_router(deps, ChatRegistry(deps.db, clock, model)))
    app.state.deps = deps
    return app
