"""Model-provider validation and local Ollama health checks."""

from __future__ import annotations

import httpx
import pytest
from langchain_ollama import ChatOllama

from job_scout.config import get_settings
from job_scout.llm import OllamaRuntimeError, get_chat_model, validate_ollama_runtime


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
