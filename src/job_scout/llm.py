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

import httpx
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from job_scout.config import get_settings


class LLMBudgetExceededError(RuntimeError):
    """Raised when a run would exceed ``MAX_LLM_CALLS_PER_RUN``."""


class OllamaRuntimeError(RuntimeError):
    """Raised when the configured local Ollama runtime is unavailable."""


def _ollama_model_name(model: str) -> str:
    """Return the Ollama model name without the LangChain provider prefix."""
    return model.removeprefix("ollama:")


def validate_ollama_runtime(model: str) -> None:
    """Verify that Ollama is reachable and the configured model is installed.

    The check uses Ollama's local ``GET /api/tags`` endpoint. Cloud providers
    return immediately without performing a network request.
    """
    if not model.startswith("ollama:"):
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


def _export_openai_key() -> None:
    """Copy the OpenAI key from settings into the environment for LangChain.

    ``pydantic-settings`` reads ``.env`` into the ``Settings`` object but does not
    export to ``os.environ``, which is where the OpenAI client looks for its key.
    """
    if os.environ.get("OPENAI_API_KEY"):
        return
    key = get_settings().openai_api_key.get_secret_value()
    if key:
        os.environ["OPENAI_API_KEY"] = key


@lru_cache(maxsize=8)
def get_chat_model(model: str, temperature: float = 0.0) -> BaseChatModel:
    """Return a cached chat model for a LangChain provider string (e.g. ``openai:gpt-4o-mini``)."""
    if model.startswith("ollama:"):
        validate_ollama_runtime(model)
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
    if model.startswith("openai:"):
        _export_openai_key()
    return init_chat_model(model, temperature=temperature)


def ensure_budget(current_calls: int, planned: int, max_calls: int) -> None:
    """Raise ``LLMBudgetExceededError`` if ``planned`` more calls would exceed ``max_calls``."""
    if current_calls + planned > max_calls:
        raise LLMBudgetExceededError(
            f"Run would make {current_calls + planned} LLM calls, exceeding MAX_LLM_CALLS_PER_RUN={max_calls}."
        )
