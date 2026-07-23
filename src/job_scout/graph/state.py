"""The LangGraph state schema threaded through every node."""

from __future__ import annotations

from typing import TypedDict

from job_scout.graph.schemas import (
    JobPosting,
    Profile,
    QueryReformulation,
    RankedJob,
    TailoringPack,
)


class AgentState(TypedDict, total=False):
    """Mutable state passed between nodes.

    ``total=False`` lets nodes return partial updates and lets the initial invoke
    payload set only the fields it has. ``llm_calls``, ``errors`` and
    ``jobs_sources`` back the call budget, non-crashing error handling and trace
    metadata respectively. ``tailoring`` and ``selected_job_id`` are Phase 2.
    """

    profile: Profile | None
    model: str
    search_query: str | None
    query_history: list[str]
    reformulation_log: list[QueryReformulation]
    jobs: list[JobPosting]
    ranked_jobs: list[RankedJob]
    ranking_batch_count: int
    ranking_workers: int
    ranking_latency_s: float
    ranking_failed_batches: int
    reformulation_count: int
    llm_calls: int
    errors: list[str]
    jobs_sources: list[str]
    tailoring: TailoringPack | None
    selected_job_id: str | None
