"""Node: extract a structured Profile from the CV text via structured output."""

from __future__ import annotations

from job_scout.config import get_settings
from job_scout.llm import ensure_budget, get_chat_model
from job_scout.prompts.extract_profile import EXTRACT_PROFILE_PROMPT
from job_scout.schemas import AgentState, Profile


def extract_profile(state: AgentState) -> dict:
    settings = get_settings()
    calls = state.get("llm_calls", 0)
    ensure_budget(calls, 1, settings.max_llm_calls_per_run)

    model = get_chat_model(settings.scout_model, temperature=0.0).with_structured_output(Profile)
    profile: Profile = model.invoke(EXTRACT_PROFILE_PROMPT.format(cv_text=state["cv_text"]))

    return {"profile": profile, "llm_calls": calls + 1}
