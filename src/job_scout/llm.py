"""Shared LLM helpers: model factory and the per-run call budget.

The budget is a deliberately visible circuit breaker. Each node reads the
running ``llm_calls`` counter from state, checks it will not exceed
``MAX_LLM_CALLS_PER_RUN`` before calling the model, and returns the incremented
total. Because the graph runs sequentially (no parallel supersteps), the plain
overwrite reducer on ``llm_calls`` is correct as long as nodes return the
cumulative total, not a delta.
"""

from __future__ import annotations

import os
from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from job_scout.config import get_settings

# Which env var each provider's client reads its key from. pydantic-settings
# loads .env into the Settings object but does NOT export to os.environ, so we
# bridge the key across here before constructing the model.
_PROVIDER_KEY_ENV = {"openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY"}


class LLMBudgetExceededError(RuntimeError):
    """Raised when a run would exceed MAX_LLM_CALLS_PER_RUN."""


def _ensure_provider_key(model: str) -> None:
    provider = model.split(":", 1)[0]
    env_var = _PROVIDER_KEY_ENV.get(provider)
    if not env_var or os.environ.get(env_var):
        return
    settings = get_settings()
    key = settings.openai_api_key if provider == "openai" else None
    if key and key.get_secret_value():
        os.environ[env_var] = key.get_secret_value()


@lru_cache(maxsize=8)
def get_chat_model(model: str, temperature: float = 0.0) -> BaseChatModel:
    """Return a cached chat model for ``model`` (a LangChain provider string)."""
    _ensure_provider_key(model)
    return init_chat_model(model, temperature=temperature)


def ensure_budget(current_calls: int, planned: int, max_calls: int) -> None:
    """Raise ``LLMBudgetExceededError`` if the next calls would blow the budget."""
    if current_calls + planned > max_calls:
        raise LLMBudgetExceededError(
            f"Run would make {current_calls + planned} LLM calls, exceeding MAX_LLM_CALLS_PER_RUN={max_calls}."
        )
