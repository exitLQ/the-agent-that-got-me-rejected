"""Chat-model factory and the per-run LLM call budget.

The call budget is a simple circuit breaker: every node reads the running
``llm_calls`` counter from state, checks it against ``MAX_LLM_CALLS_PER_RUN``
before calling the model, and returns the incremented total. The graph runs
sequentially, so returning the cumulative total (not a delta) keeps the counter
correct.
"""

from __future__ import annotations

import os
from functools import lru_cache
from importlib.util import find_spec

import httpx
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from job_scout.config import get_settings


class LLMBudgetExceededError(RuntimeError):
    """Raised when a run would exceed ``MAX_LLM_CALLS_PER_RUN``."""


class OllamaRuntimeError(RuntimeError):
    """Raised when the configured local Ollama runtime is unavailable."""


class ModelConfigurationError(RuntimeError):
    """Raised when a model provider is unsupported or not safely configured."""


_CLOUD_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "groq": "GROQ_API_KEY",
}
_PROVIDER_PACKAGE = {
    "openai": "langchain_openai",
    "anthropic": "langchain_anthropic",
    "xai": "langchain_xai",
    "groq": "langchain_groq",
}


def model_provider(model: str) -> str:
    """Return the normalized provider prefix from ``provider:model``."""
    provider, separator, name = model.partition(":")
    return provider.strip().casefold() if separator and name.strip() else ""


def _ollama_model_name(model: str) -> str:
    """Return the Ollama model name without the LangChain provider prefix."""
    provider, separator, name = model.partition(":")
    if separator and provider.strip().casefold() == "ollama":
        return name.strip()
    return model.strip()


def _normalized_model(model: str) -> str:
    """Normalize a valid provider prefix while preserving the model identifier."""
    provider = model_provider(model)
    if not provider:
        return model.strip()
    return f"{provider}:{model.partition(':')[2].strip()}"


def validate_ollama_runtime(model: str) -> None:
    """Verify that Ollama is reachable and the configured model is installed.

    The check uses Ollama's local ``GET /api/tags`` endpoint. Cloud providers
    return immediately without performing a network request.
    """
    if model_provider(model) != "ollama":
        return

    settings = get_settings()
    model_name = _ollama_model_name(model)
    endpoint = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        response = httpx.get(endpoint, timeout=settings.ollama_health_timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Ollama returned an unexpected response")
    except (httpx.HTTPError, ValueError) as exc:
        raise OllamaRuntimeError(
            "Ollama is not reachable. Start Ollama and verify "
            f"{settings.ollama_base_url}. Original error: {exc}"
        ) from exc

    installed = {
        str(item.get("name") or item.get("model"))
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }
    if model_name not in installed:
        available = ", ".join(sorted(installed)) or "none"
        raise OllamaRuntimeError(
            f"Ollama model '{model_name}' is not installed. Run 'ollama pull {model_name}'. "
            f"Installed models: {available}."
        )


def _provider_key(provider: str) -> str:
    """Return a configured provider key without logging or displaying it."""
    settings = get_settings()
    keys = {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "xai": settings.xai_api_key,
        "groq": settings.groq_api_key,
    }
    secret = keys.get(provider)
    return secret.get_secret_value() if secret else ""


def _export_provider_key(provider: str) -> None:
    """Copy a configured provider key into the environment for LangChain.

    ``pydantic-settings`` reads ``.env`` into the ``Settings`` object but does not
    export to ``os.environ``, where provider clients look for their keys.
    """
    env_name = _CLOUD_KEY_ENV[provider]
    if os.environ.get(env_name):
        return
    key = _provider_key(provider)
    if key:
        os.environ[env_name] = key


def validate_model_configuration(model: str) -> str:
    """Validate provider, network opt-in, and credentials before model creation."""
    provider = model_provider(model)
    if provider == "ollama":
        validate_ollama_runtime(model)
        return provider
    if provider not in _CLOUD_KEY_ENV:
        supported = "ollama, openai, anthropic, xai, groq"
        raise ModelConfigurationError(
            f"Unsupported SCOUT_MODEL '{model}'. Use provider:model with one of: {supported}."
        )

    settings = get_settings()
    if settings.offline_mode:
        raise ModelConfigurationError(
            f"SCOUT_MODEL '{model}' requires network access, but OFFLINE_MODE=true. "
            "Use an Ollama model or explicitly set OFFLINE_MODE=false."
        )
    if not settings.cloud_llm_enabled:
        raise ModelConfigurationError(
            f"SCOUT_MODEL '{model}' is a cloud model. Set CLOUD_LLM_ENABLED=true "
            "to confirm that resume and job content may leave this machine."
        )
    env_name = _CLOUD_KEY_ENV[provider]
    if not (os.environ.get(env_name) or _provider_key(provider)):
        raise ModelConfigurationError(
            f"{env_name} is required for SCOUT_MODEL '{model}'. Add it to .env without committing the file."
        )
    if find_spec(_PROVIDER_PACKAGE[provider]) is None:
        raise ModelConfigurationError(
            f"Support for provider '{provider}' is not installed. "
            "Run 'uv sync --all-extras --all-groups'."
        )
    _export_provider_key(provider)
    return provider


@lru_cache(maxsize=8)
def get_chat_model(model: str, temperature: float = 0.0) -> BaseChatModel:
    """Return a cached chat model for a LangChain provider string (e.g. ``openai:gpt-4o-mini``)."""
    provider = validate_model_configuration(model)
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise OllamaRuntimeError(
                "Ollama support is not installed. Run 'uv sync --extra ollama --all-groups'."
            ) from exc
        settings = get_settings()
        return ChatOllama(
            model=_ollama_model_name(model),
            temperature=temperature,
            base_url=settings.ollama_base_url,
        )
    try:
        return init_chat_model(_normalized_model(model), temperature=temperature)
    except ImportError as exc:
        raise ModelConfigurationError(
            f"Support for provider '{provider}' is not installed. "
            "Run 'uv sync --all-extras --all-groups'."
        ) from exc


def ensure_budget(current_calls: int, planned: int, max_calls: int) -> None:
    """Raise ``LLMBudgetExceededError`` if ``planned`` more calls would exceed ``max_calls``."""
    if current_calls + planned > max_calls:
        raise LLMBudgetExceededError(
            f"Run would make {current_calls + planned} LLM calls, exceeding MAX_LLM_CALLS_PER_RUN={max_calls}."
        )
