"""Generate a strictly typed, corpus-linked application draft for one job."""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from job_scout.config import get_settings
from job_scout.graph.prompts.tailor import TAILOR_PROMPT, TAILOR_SYSTEM_PROMPT
from job_scout.graph.schemas import RankedJob, TailoringPack
from job_scout.graph.state import AgentContext, AgentState
from job_scout.llm import ensure_budget, get_chat_model

MAX_CORPUS_ITEMS = 120
MAX_ERROR_LENGTH = 240
_SECRET_VALUE = re.compile(
    r"(?i)\b(?:api[_-]?key|authorization|bearer)\b(?:\s*[:=]\s*|\s+)\S+"
)
_TOKEN_VALUE = re.compile(r"\b(?:sk|xai|gsk)[-_][A-Za-z0-9_-]{8,}\b")


def _selected_job(state: AgentState) -> RankedJob | None:
    selected_job_id = state.get("selected_job_id")
    if not selected_job_id:
        return None
    return next(
        (
            ranked
            for ranked in state.get("ranked_jobs", [])
            if ranked.job.job_id == selected_job_id
        ),
        None,
    )


def _bounded_error(prefix: str, exc: Exception) -> str:
    detail = " ".join(str(exc).split())[:MAX_ERROR_LENGTH]
    detail = _SECRET_VALUE.sub("[redacted credential]", detail)
    detail = _TOKEN_VALUE.sub("[redacted credential]", detail)
    return f"tailor: {prefix}: {type(exc).__name__}: {detail}"


def _prompt(state: AgentState, ranked: RankedJob, context: AgentContext) -> str:
    profile = state["profile"]
    profile_payload = {
        "seniority": profile.seniority,
        "primary_roles": profile.primary_roles,
        "skills": profile.skills,
        "years_experience": profile.years_experience,
        "languages": profile.languages,
    }
    job = ranked.job
    job_payload = {
        "job_id": job.job_id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote,
        "description": job.description[:6000],
        "tags": job.tags,
    }
    corpus_payload = [
        item.model_dump()
        for item in context.candidate_corpus[:MAX_CORPUS_ITEMS]
    ]
    return TAILOR_PROMPT.format(
        profile_json=json.dumps(profile_payload, ensure_ascii=False, sort_keys=True),
        job_json=json.dumps(job_payload, ensure_ascii=False, sort_keys=True),
        corpus_json=json.dumps(corpus_payload, ensure_ascii=False, sort_keys=True),
    )


def tailor_application(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict:
    """Return a grounded tailoring pack or a bounded, non-crashing error."""
    errors = list(state.get("errors", []))
    calls = state.get("llm_calls", 0)
    selected_job_id = state.get("selected_job_id")
    if not selected_job_id:
        errors.append("tailor: no job was selected")
        return {"tailoring": None, "errors": errors}

    ranked = _selected_job(state)
    if ranked is None:
        safe_job_id = " ".join(str(selected_job_id).split())[:100]
        errors.append(f"tailor: selected job '{safe_job_id}' is not available")
        return {"tailoring": None, "errors": errors}
    if state.get("profile") is None:
        errors.append("tailor: candidate profile is unavailable")
        return {"tailoring": None, "errors": errors}

    context = runtime.context
    if context is None or not context.candidate_corpus:
        errors.append("tailor: temporary CV corpus is unavailable; upload the CV again")
        return {"tailoring": None, "errors": errors}

    settings = get_settings()
    attempted = False
    try:
        ensure_budget(calls, 1, settings.max_llm_calls_per_run)
        model_name = context.tailor_model or settings.scout_tailor_model
        model = get_chat_model(model_name, temperature=0.0).with_structured_output(
            TailoringPack
        )
        attempted = True
        generated = model.invoke(
            [
                SystemMessage(TAILOR_SYSTEM_PROMPT),
                HumanMessage(_prompt(state, ranked, context)),
            ]
        )
        pack = (
            generated
            if isinstance(generated, TailoringPack)
            else TailoringPack.model_validate(generated)
        )
        calls += 1
    except Exception as exc:  # noqa: BLE001 - convert provider/schema failures into state
        if attempted:
            calls += 1
        errors.append(_bounded_error("generation failed", exc))
        return {"tailoring": None, "errors": errors, "llm_calls": calls}

    if pack.selected_job_id != selected_job_id:
        errors.append("tailor: generated pack referenced a different job")
        return {"tailoring": None, "errors": errors, "llm_calls": calls}
    return {"tailoring": pack, "errors": errors, "llm_calls": calls}
