"""Pydantic models used across the agent graph.

These are the structured-output targets for the LLM/tool calls and the shared
data contracts the nodes read and write. Phase 2 models (``EmphasisItem``,
``TailoringPack``) are defined here already so the state (and therefore the
checkpoint format) is stable across phases.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Seniority = Literal["junior", "mid", "senior", "lead", "unknown"]
JobSourceName = Literal["jsearch", "adzuna", "remotive", "cache"]


class Profile(BaseModel):
    """Structured candidate profile extracted from a CV."""

    name: str | None = None
    seniority: Seniority = "unknown"
    primary_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    years_experience: float | None = None
    locations: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    remote_ok: bool = False
    raw_summary: str = ""


class JobPosting(BaseModel):
    """A single job opening, normalized across all sources."""

    job_id: str
    title: str
    company: str
    location: str
    remote: bool = False
    description: str = ""
    url: str = ""
    tags: list[str] = Field(default_factory=list)
    source: JobSourceName


class JobScore(BaseModel):
    """The ranking LLM's score for one job, keyed back to a posting by id."""

    job_id: str
    fit_score: int = Field(ge=0, le=100)
    fit_explanation: str
    matched_skills: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class JobScores(BaseModel):
    """Structured-output container for a batch of ``JobScore``."""

    scores: list[JobScore]


class ScoreBreakdown(BaseModel):
    """Auditable inputs to the final hybrid fit score."""

    llm: int = Field(ge=0, le=100)
    deterministic: int = Field(ge=0, le=100)
    skills: int = Field(ge=0, le=100)
    role: int = Field(ge=0, le=100)
    seniority: int = Field(ge=0, le=100)
    location: int = Field(ge=0, le=100)


class SkillEvidence(BaseModel):
    """A displayed skill claim with profile-side and job-side provenance."""

    skill: str
    profile_evidence: str
    job_evidence: str


class QueryReformulation(BaseModel):
    """Auditable record of one controlled query-broadening decision."""

    attempt: int = Field(ge=1)
    previous_query: str
    query: str
    strategy: Literal["model", "fallback"]
    reason: str
    jobs_seen: int = Field(ge=0)
    good_jobs: int = Field(ge=0)
    best_score: int = Field(ge=0, le=100)


class RankedJob(BaseModel):
    """A job scored against the candidate profile."""

    job: JobPosting
    fit_score: int = Field(ge=0, le=100)
    fit_explanation: str
    matched_skills: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    score_breakdown: ScoreBreakdown | None = None
    matched_skill_evidence: list[SkillEvidence] = Field(default_factory=list)
    gap_evidence: list[SkillEvidence] = Field(default_factory=list)


class EmphasisItem(BaseModel):
    """A CV bullet to promote or reword for a specific posting (Phase 2)."""

    original_bullet: str
    suggested_rewrite: str
    reason: str


class TailoringPack(BaseModel):
    """Application material generated for a selected job (Phase 2)."""

    cover_letter: str
    cv_emphasis: list[EmphasisItem] = Field(default_factory=list)
    honesty_note: str = ""
