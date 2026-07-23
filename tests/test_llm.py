"""Model-provider validation and local Ollama health checks."""

from __future__ import annotations

import httpx
import pytest
from langchain_ollama import ChatOllama

from job_scout.config import get_settings
from job_scout.llm import (
    ModelConfigurationError,
    OllamaRuntimeError,
    get_chat_model,
    model_configuration_status,
    model_provider,
    qualify_model,
    validate_model_configuration,
    validate_ollama_runtime,
)


def test_cloud_model_skips_ollama_health_check(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Ollama health endpoint must not be called")

    monkeypatch.setattr(httpx, "get", fail_if_called)
    validate_ollama_runtime("openai:gpt-4o-mini")


def test_ollama_health_check_accepts_installed_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434")
    get_settings.cache_clear()

    def fake_get(url, timeout):
        assert url == "http://ollama.test:11434/api/tags"
        assert timeout == 3.0
        return httpx.Response(
            200,
            json={"models": [{"name": "qwen3:8b", "model": "qwen3:8b"}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    validate_ollama_runtime("ollama:qwen3:8b")


def test_ollama_health_check_reports_missing_model(monkeypatch):
    def fake_get(url, timeout):
        return httpx.Response(
            200,
            json={"models": [{"name": "gemma3:4b"}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(OllamaRuntimeError, match=r"ollama pull qwen3:8b"):
        validate_ollama_runtime("ollama:qwen3:8b")


def test_ollama_health_check_reports_unreachable_service(monkeypatch):
    def fake_get(url, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(OllamaRuntimeError, match="Ollama is not reachable"):
        validate_ollama_runtime("ollama:qwen3:8b")


def test_get_chat_model_builds_chat_ollama(monkeypatch):
    monkeypatch.setattr("job_scout.llm.validate_ollama_runtime", lambda model: None)
    get_chat_model.cache_clear()
    model = get_chat_model("ollama:qwen3:8b")
    assert isinstance(model, ChatOllama)
    assert model.model == "qwen3:8b"
    get_chat_model.cache_clear()


def test_ollama_provider_prefix_is_normalized(monkeypatch):
    monkeypatch.setattr("job_scout.llm.validate_ollama_runtime", lambda model: None)
    get_chat_model.cache_clear()

    model = get_chat_model("OLLAMA:qwen3:8b")

    assert isinstance(model, ChatOllama)
    assert model.model == "qwen3:8b"
    get_chat_model.cache_clear()


def test_cloud_provider_prefix_is_normalized(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "false")
    monkeypatch.setenv("CLOUD_LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    get_settings.cache_clear()
    get_chat_model.cache_clear()
    calls = []
    monkeypatch.setattr(
        "job_scout.llm.init_chat_model",
        lambda selected, temperature: calls.append((selected, temperature)) or object(),
    )

    get_chat_model(" OpenAI : gpt-5-mini ")

    assert calls == [("openai:gpt-5-mini", 0.0)]
    get_chat_model.cache_clear()


@pytest.mark.parametrize(
    ("provider", "model_name", "expected"),
    [
        ("ollama", "qwen3:8b", "ollama:qwen3:8b"),
        ("OLLAMA", "ollama:qwen3:8b", "ollama:qwen3:8b"),
        (" OpenAI ", " gpt-5-mini ", "openai:gpt-5-mini"),
    ],
)
def test_qualify_model_builds_a_canonical_session_model(provider, model_name, expected):
    assert qualify_model(provider, model_name) == expected


def test_model_status_explains_offline_cloud_block(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "true")
    monkeypatch.setenv("CLOUD_LLM_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "configured")
    get_settings.cache_clear()

    status = model_configuration_status("anthropic:claude-sonnet-4-6")

    assert status.ready is False
    assert status.external is True
    assert status.message == "Blocked by OFFLINE_MODE=true."


def test_model_status_reports_ready_cloud_provider(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "false")
    monkeypatch.setenv("CLOUD_LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "configured")
    get_settings.cache_clear()

    status = model_configuration_status("openai:gpt-5-mini")

    assert status.ready is True
    assert status.external is True
    assert "will be sent to openai" in status.message


@pytest.mark.parametrize(
    ("model", "provider"),
    [
        ("ollama:qwen3:8b", "ollama"),
        ("OLLAMA:qwen3:8b", "ollama"),
        ("openai:gpt-5-mini", "openai"),
        ("anthropic:claude-sonnet-4-6", "anthropic"),
        ("xai:grok-4.3", "xai"),
    ],
)
def test_model_provider(model, provider):
    assert model_provider(model) == provider


@pytest.mark.parametrize(
    ("model", "key_name"),
    [
        ("openai:gpt-5-mini", "OPENAI_API_KEY"),
        ("anthropic:claude-sonnet-4-6", "ANTHROPIC_API_KEY"),
        ("xai:grok-4.3", "XAI_API_KEY"),
    ],
)
def test_cloud_provider_is_created_with_explicit_consent(monkeypatch, model, key_name):
    sentinel = object()
    monkeypatch.setenv("OFFLINE_MODE", "false")
    monkeypatch.setenv("CLOUD_LLM_ENABLED", "true")
    monkeypatch.setenv(key_name, "test-secret")
    get_settings.cache_clear()
    get_chat_model.cache_clear()
    calls = []
    monkeypatch.setattr(
        "job_scout.llm.init_chat_model",
        lambda selected, temperature: calls.append((selected, temperature)) or sentinel,
    )

    assert get_chat_model(model, 0.25) is sentinel
    assert calls == [(model, 0.25)]
    get_chat_model.cache_clear()


@pytest.mark.parametrize(
    "model",
    [
        "openai:gpt-5-mini",
        "anthropic:claude-sonnet-4-6",
        "xai:grok-4.3",
    ],
)
def test_offline_mode_blocks_cloud_models(monkeypatch, model):
    monkeypatch.setenv("OFFLINE_MODE", "true")
    monkeypatch.setenv("CLOUD_LLM_ENABLED", "true")
    get_settings.cache_clear()

    with pytest.raises(ModelConfigurationError, match="OFFLINE_MODE=true"):
        validate_model_configuration(model)


def test_cloud_model_requires_explicit_consent(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "false")
    monkeypatch.setenv("CLOUD_LLM_ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(ModelConfigurationError, match="CLOUD_LLM_ENABLED=true"):
        validate_model_configuration("anthropic:claude-sonnet-4-6")


def test_cloud_model_requires_matching_key(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "false")
    monkeypatch.setenv("CLOUD_LLM_ENABLED", "true")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ModelConfigurationError, match="XAI_API_KEY"):
        validate_model_configuration("xai:grok-4.3")


def test_unsupported_provider_is_rejected():
    with pytest.raises(ModelConfigurationError, match="Unsupported SCOUT_MODEL"):
        validate_model_configuration("unknown:model")


def test_missing_provider_package_is_actionable(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "false")
    monkeypatch.setenv("CLOUD_LLM_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "configured")
    monkeypatch.setattr("job_scout.llm.find_spec", lambda package: None)
    get_settings.cache_clear()

    with pytest.raises(ModelConfigurationError, match="uv sync --all-extras"):
        validate_model_configuration("anthropic:claude-sonnet-4-6")
