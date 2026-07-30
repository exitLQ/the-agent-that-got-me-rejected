"""Graph node for deterministic post-generation grounding checks."""

from __future__ import annotations

import re

from langgraph.runtime import Runtime

from job_scout.graph.state import AgentContext, AgentState
from job_scout.validation import validate_pack


def validate_tailoring(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict:
    """Attach a deterministic fabrication report when a draft exists."""
    pack = state.get("tailoring")
    if pack is None:
        return {"fabrication_report": None}

    selected_job_id = state.get("selected_job_id")
    ranked = next(
        (
            item
            for item in state.get("ranked_jobs", [])
            if item.job.job_id == selected_job_id
        ),
        None,
    )
    job_context = []
    if ranked is not None:
        job = ranked.job
        job_context = [
            job.title,
            job.company,
            job.location,
            *job.tags,
            *_split_job_context(job.description),
        ]
    context = runtime.context or AgentContext()
    report = validate_pack(
        pack,
        context.candidate_corpus,
        job_context=job_context,
    )
    return {"fabrication_report": report}


def _split_job_context(description: str) -> list[str]:
    """Bound job reference text into sentence-like deterministic fragments."""
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|\n+", description[:6000])
        if part.strip()
    ]
