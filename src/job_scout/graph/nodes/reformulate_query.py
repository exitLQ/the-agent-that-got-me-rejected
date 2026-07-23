"""Broaden the search query when too few good matches came back.

Validates novelty and shape, falls back deterministically when needed, records
quality diagnostics, and writes the query that fetch_jobs executes directly.
"""

from __future__ import annotations

from collections import Counter

from job_scout.config import get_settings
from job_scout.graph.prompts.reformulate import REFORMULATE_PROMPT
from job_scout.graph.schemas import QueryReformulation
from job_scout.graph.state import AgentState
from job_scout.llm import ensure_budget, get_chat_model
from job_scout.query_optimizer import fallback_query, query_key, sanitize_query

GOOD_FIT_THRESHOLD = 60


def _result_diagnostics(state: AgentState) -> tuple[str, int, int, int]:
    """Summarize result quality without sending job descriptions to the model."""
    ranked = state.get("ranked_jobs", [])
    good_jobs = sum(item.fit_score >= GOOD_FIT_THRESHOLD for item in ranked)
    best_score = max((item.fit_score for item in ranked), default=0)
    top = ", ".join(
        f"{item.job.title} ({item.fit_score})"
        for item in sorted(ranked, key=lambda item: item.fit_score, reverse=True)[:3]
    ) or "none"
    gaps = Counter(gap for item in ranked for gap in item.gaps)
    common_gaps = ", ".join(gap for gap, _count in gaps.most_common(4)) or "none"
    diagnostics = (
        f"jobs seen: {len(ranked)}; good jobs at or above {GOOD_FIT_THRESHOLD}: "
        f"{good_jobs}; best score: {best_score}; top results: {top}; "
        f"common grounded gaps: {common_gaps}"
    )
    return diagnostics, len(ranked), good_jobs, best_score


def reformulate_query(state: AgentState) -> dict:
    """Produce one validated, novel broader query and record the decision."""
    settings = get_settings()
    calls = state.get("llm_calls", 0)
    ensure_budget(calls, 1, settings.max_llm_calls_per_run)
    profile = state["profile"]
    previous_query = state.get("search_query") or ""
    history = list(state.get("query_history", []))
    if previous_query and query_key(previous_query) not in {query_key(item) for item in history}:
        history.append(previous_query)
    attempt = state.get("reformulation_count", 0) + 1
    diagnostics, jobs_seen, good_jobs, best_score = _result_diagnostics(state)

    prompt = REFORMULATE_PROMPT.format(
        profile=", ".join(profile.primary_roles + profile.skills[:10]),
        previous_query=previous_query,
        query_history=", ".join(history) or "none",
        diagnostics=diagnostics,
        attempt=attempt,
    )
    proposal = get_chat_model(settings.scout_model, temperature=0.0).invoke(prompt).content
    new_query = sanitize_query(str(proposal))
    strategy = "model"
    reason = "accepted a short, novel model proposal"
    history_keys = {query_key(item) for item in history}
    if not new_query:
        strategy = "fallback"
        reason = "rejected invalid or overly long model output"
    elif query_key(new_query) in history_keys:
        strategy = "fallback"
        reason = "rejected a query already present in history"
    if strategy == "fallback":
        new_query = fallback_query(profile, history, attempt=attempt)

    log = list(state.get("reformulation_log", []))
    log.append(
        QueryReformulation(
            attempt=attempt,
            previous_query=previous_query,
            query=new_query,
            strategy=strategy,
            reason=reason,
            jobs_seen=jobs_seen,
            good_jobs=good_jobs,
            best_score=best_score,
        )
    )

    return {
        "search_query": new_query,
        "reformulation_count": attempt,
        "reformulation_log": log,
        "llm_calls": calls + 1,
    }
