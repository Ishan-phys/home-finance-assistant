import pytest
from cfo.api.app import ProviderConfigError, build_categorizer, build_chat_model
from cfo.api.config import Settings
from cfo.categorize.categorizer import AnthropicClient
from cfo.categorize.decisions import DecisionsCategorizer


def settings(**env: str) -> Settings:
    import os

    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        return Settings.from_env()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def clear_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_the_one_key_set_picks_the_provider_for_categorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_keys(monkeypatch)
    assert build_categorizer(settings()) is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert isinstance(build_categorizer(settings()), AnthropicClient)
    assert build_categorizer(settings(CATEGORIZER="none")) is None
    clear_keys(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    chosen = build_categorizer(settings(DECISIONS_THRESHOLD="0.8"))
    assert isinstance(chosen, DecisionsCategorizer)
    assert (chosen.model, chosen.threshold) == ("gpt-6-luna", 0.8)


def test_the_one_key_set_picks_the_chat_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from google.adk.models.anthropic_llm import AnthropicLlm
    from google.adk.models.lite_llm import LiteLlm

    clear_keys(monkeypatch)
    assert isinstance(build_chat_model(settings()), AnthropicLlm)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    chosen = build_chat_model(settings())
    assert isinstance(chosen, LiteLlm) and chosen.model == "openai/gpt-5.5"
    custom = build_chat_model(settings(CHAT_MODEL="gpt-x"))
    assert isinstance(custom, LiteLlm) and custom.model == "openai/gpt-x"


def test_both_keys_is_refused_with_a_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    for build in (build_categorizer, build_chat_model):
        with pytest.raises(ProviderConfigError, match="set only one"):
            build(settings())
