"""Pydantic models and the LangGraph state schema.

These are the contracts every node reads and writes. ``Profile``, ``JobPosting``
and ``RankedJob`` are LLM/tool structured-output targets; ``AgentState`` is the
single mutable state object threaded through the graph. Phase 2 fields
(``tailoring``, ``selected_job_id``) already live here so the state schema — and
therefore the checkpoint format — does not change between phases.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

Seniority = Literal["junior", "mid", "senior", "lead", "unknown"]
JobSourceName = Literal["adzuna", "remotive", "cache"]


class Profile(BaseModel):
    """Structured candidate profile extracted from a CV."""

    name: str | None = None
    seniority: Seniority = "unknown"
    primary_roles: list[str] = Field(default_factory=list)  # e.g. ["ML Engineer"]
    skills: list[str] = Field(default_factory=list)  # normalized, lowercase
    years_experience: float | None = None
    locations: list[str] = Field(default_factory=list)  # acceptable locations
    languages: list[str] = Field(default_factory=list)  # spoken languages
    remote_ok: bool = False
    raw_summary: str = ""  # 3-4 sentence LLM summary of the CV


class JobPosting(BaseModel):
    """A single job opening, normalized across all sources."""

    job_id: str
    title: str
    company: str
    location: str
    remote: bool = False
    description: str = ""  # truncated to 4000 chars at ingestion
    url: str = ""
    tags: list[str] = Field(default_factory=list)
    source: JobSourceName


class RankedJob(BaseModel):
    """A job scored against the candidate profile by the ranking LLM."""

    job: JobPosting
    fit_score: int = Field(ge=0, le=100)
    fit_explanation: str  # 2-4 sentences
    matched_skills: list[str] = Field(default_factory=list)  # subset of profile.skills ∩ job
    gaps: list[str] = Field(default_factory=list)  # requirements the candidate lacks


# --- Phase 2 stubs (defined now so state/checkpoint format is stable) --------


class EmphasisItem(BaseModel):
    """One CV bullet to promote/reword for a specific posting (Phase 2)."""

    original_bullet: str  # verbatim from CV text
    suggested_rewrite: str
    reason: str  # tied to a specific job requirement


class TailoringPack(BaseModel):
    """Application material generated for a selected job (Phase 2)."""

    cover_letter: str  # <= 350 words
    cv_emphasis: list[EmphasisItem] = Field(default_factory=list)
    honesty_note: str = ""


class AgentState(TypedDict, total=False):
    """Mutable state threaded through the graph.

    ``total=False`` so nodes can return partial updates and the initial invoke
    payload need only set the fields it has. Bookkeeping fields
    (``llm_calls``, ``errors``, ``jobs_sources``) support the circuit breaker,
    non-crashing error handling, and trace metadata respectively.
    """

    cv_text: str
    profile: Profile | None
    search_query: str | None
    jobs: list[JobPosting]
    ranked_jobs: list[RankedJob]
    reformulation_count: int  # loop guard
    llm_calls: int  # circuit-breaker counter
    errors: list[str]  # accumulated non-fatal node errors
    jobs_sources: list[str]  # which adapters served the last fetch
    # --- Phase 2 ---
    tailoring: TailoringPack | None
    selected_job_id: str | None
