"""Fetch jobs from an initial tool decision or a validated retry query.

On the first pass, the LLM reads the profile and selects the query, country, and
remote flag. A reformulation retry executes its already validated query directly
without a second model decision.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from job_scout.config import get_settings
from job_scout.graph.schemas import JobPosting
from job_scout.graph.state import AgentState
from job_scout.llm import ensure_budget, get_chat_model
from job_scout.query_optimizer import fallback_query, query_key, sanitize_query
from job_scout.tools.jobs_api import run_search, search_jobs

CAP = 25

_SYSTEM = (
    "You are a job search assistant. Call the search_jobs tool exactly once. "
    "Build the query around the candidate's most recent and most relevant "
    "experience — their current or latest role and strongest skills, at the right "
    "seniority — rather than a broad catch-all or an older, adjacent role. "
    "Pick a country code from their location and set the remote flag from their preference."
)


def _build_prompt(state: AgentState) -> str:
    """Describe the candidate to the LLM, adding reformulation guidance if looping."""
    profile = state["profile"]
    lines = [
        f"Seniority: {profile.seniority}",
        f"Recent / primary roles: {', '.join(profile.primary_roles) or 'unknown'}",
        f"Key skills: {', '.join(profile.skills[:15])}",
        f"Summary: {profile.raw_summary or 'n/a'}",
        f"Locations: {', '.join(profile.locations) or 'unknown'}",
        f"Open to remote: {profile.remote_ok}",
    ]
    return "\n".join(lines)


def fetch_jobs(state: AgentState) -> dict:
    """Run the job search with LLM-chosen arguments and merge results into state."""
    settings = get_settings()
    calls = state.get("llm_calls", 0)
    profile = state["profile"]
    errors = list(state.get("errors", []))
    location = profile.locations[0] if profile.locations else None
    is_retry = state.get("reformulation_count", 0) > 0
    if is_retry and state.get("search_query"):
        query = sanitize_query(state["search_query"]) or fallback_query(
            profile,
            state.get("query_history", []),
            attempt=state.get("reformulation_count", 0),
        )
        country = None
        remote = profile.remote_ok
    else:
        ensure_budget(calls, 1, settings.max_llm_calls_per_run)
        model = get_chat_model(state.get("model", settings.scout_model), temperature=0.0).bind_tools([search_jobs])
        message = model.invoke([SystemMessage(_SYSTEM), HumanMessage(_build_prompt(state))])
        calls += 1
        if message.tool_calls:
            args = message.tool_calls[0]["args"]
            query = sanitize_query(args.get("query"))
            country = args.get("country")
            remote = bool(args.get("remote", profile.remote_ok))
        else:
            query = None
            country = None
            remote = profile.remote_ok
            errors.append("fetch_jobs: LLM issued no tool call; used profile-derived query")
        if not query:
            query = fallback_query(profile, state.get("query_history", []), attempt=0)
            errors.append("fetch_jobs: invalid query; used deterministic fallback")

    jobs, sources = run_search(
        query=query,
        location=location,
        country=country,
        remote=remote,
        limit=CAP,
        preferred_locations=profile.locations,
    )
    jobs = _dedupe_with_existing(
        state.get("jobs", []),
        jobs,
        prefer_new=is_retry,
    )[:CAP]
    history = list(state.get("query_history", []))
    if query_key(query) not in {query_key(item) for item in history}:
        history.append(query)

    return {
        "jobs": jobs,
        "search_query": query,
        "query_history": history,
        "jobs_sources": sources,
        "errors": errors,
        "llm_calls": calls,
    }


def _dedupe_with_existing(
    existing: list[JobPosting],
    new: list[JobPosting],
    *,
    prefer_new: bool = False,
) -> list[JobPosting]:
    """Merge results without duplicates, prioritizing novel retry results."""
    ordered = [*new, *existing] if prefer_new else [*existing, *new]
    seen: set[tuple[str, str]] = set()
    merged: list[JobPosting] = []
    for job in ordered:
        key = (job.title.strip().lower(), job.company.strip().lower())
        if key not in seen:
            seen.add(key)
            merged.append(job)
    return merged
