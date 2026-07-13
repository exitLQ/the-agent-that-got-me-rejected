"""Node: an LLM with the search_jobs tool bound decides the search arguments.

This is the tool-usage lesson: the LLM reads the profile and *chooses* the query
string, country and remote flag (sometimes suboptimally — that is deliberate
trace material). We then execute the search with those arguments and land the
results in state. On a reformulation loop the reformulated query is passed as
strong guidance and the LLM issues a fresh tool call.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from job_scout.config import get_settings
from job_scout.llm import ensure_budget, get_chat_model
from job_scout.schemas import AgentState, JobPosting
from job_scout.tools.jobs_api import run_search, search_jobs

CAP = 25

_SYSTEM = (
    "You are a job search assistant. Call the search_jobs tool exactly once with "
    "good arguments for this candidate. Choose a query, an optional country code, "
    "and whether to include remote roles."
)


def _build_prompt(state: AgentState) -> str:
    profile = state["profile"]
    lines = [
        f"Candidate roles: {', '.join(profile.primary_roles) or 'unknown'}",
        f"Skills: {', '.join(profile.skills[:15])}",
        f"Locations: {', '.join(profile.locations) or 'unknown'}",
        f"Open to remote: {profile.remote_ok}",
    ]
    reformulated = state.get("search_query")
    if state.get("reformulation_count", 0) and reformulated:
        lines.append(
            f"\nThe previous search returned too few good matches. Use this broader query and search again: {reformulated!r}"
        )
    return "\n".join(lines)


def fetch_jobs(state: AgentState) -> dict:
    settings = get_settings()
    calls = state.get("llm_calls", 0)
    ensure_budget(calls, 1, settings.max_llm_calls_per_run)
    profile = state["profile"]
    errors = list(state.get("errors", []))

    model = get_chat_model(settings.scout_model, temperature=0.0).bind_tools([search_jobs])
    message = model.invoke([SystemMessage(_SYSTEM), HumanMessage(_build_prompt(state))])
    calls += 1

    location = profile.locations[0] if profile.locations else None
    if message.tool_calls:
        args = message.tool_calls[0]["args"]
        query = args.get("query") or " ".join(profile.primary_roles[:2])
        country = args.get("country")
        remote = bool(args.get("remote", profile.remote_ok))
    else:
        # Honest first-draft behaviour: the model didn't call the tool. Fall back
        # to profile-derived defaults and record it for the trace/findings.
        errors.append("fetch_jobs: LLM issued no tool call; used profile-derived query")
        query = " ".join(profile.primary_roles[:2]) or " ".join(profile.skills[:3])
        country = None
        remote = profile.remote_ok

    jobs, sources = run_search(query=query, location=location, country=country, remote=remote, limit=CAP)
    jobs = _dedupe_with_existing(state.get("jobs", []), jobs)[:CAP]

    return {
        "jobs": jobs,
        "search_query": query,
        "jobs_sources": sources,
        "errors": errors,
        "llm_calls": calls,
    }


def _dedupe_with_existing(existing: list[JobPosting], new: list[JobPosting]) -> list[JobPosting]:
    """On a reformulation loop, merge new results with prior ones, deduped."""
    seen = {(j.title.strip().lower(), j.company.strip().lower()) for j in existing}
    merged = list(existing)
    for job in new:
        key = (job.title.strip().lower(), job.company.strip().lower())
        if key not in seen:
            seen.add(key)
            merged.append(job)
    return merged
