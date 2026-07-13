"""Shared LLM helpers: model factory and the per-run call budget.

The budget is a deliberately visible circuit breaker. Each node reads the
running ``llm_calls`` counter from state, checks it will not exceed
``MAX_LLM_CALLS_PER_RUN`` before calling the model, and returns the incremented
total. Because the graph runs sequentially (no parallel supersteps), the plain
overwrite reducer on ``llm_calls`` is correct as long as nodes return the
cumulative total, not a delta.
"""

from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel


class LLMBudgetExceededError(RuntimeError):
    """Raised when a run would exceed MAX_LLM_CALLS_PER_RUN."""


@lru_cache(maxsize=8)
def get_chat_model(model: str, temperature: float = 0.0) -> BaseChatModel:
    """Return a cached chat model for ``model`` (a LangChain provider string)."""
    return init_chat_model(model, temperature=temperature)


def ensure_budget(current_calls: int, planned: int, max_calls: int) -> None:
    """Raise ``LLMBudgetExceededError`` if the next calls would blow the budget."""
    if current_calls + planned > max_calls:
        raise LLMBudgetExceededError(
            f"Run would make {current_calls + planned} LLM calls, exceeding MAX_LLM_CALLS_PER_RUN={max_calls}."
        )
