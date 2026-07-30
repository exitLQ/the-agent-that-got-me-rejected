"""Pydantic models used across the agent graph.

These are the structured-output targets for the LLM/tool calls and the shared
data contracts the nodes read and write. Application-tailoring models use
strict fields and mandatory corpus references so later generation is
mechanically checkable.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


CorpusReference = Annotated[
    str,
    Field(pattern=r"^cv-(?:experience|skill|education|summary)-\d{3}$"),
]
RequirementText = Annotated[str, Field(min_length=3, max_length=300)]


class _StrictTailoringModel(BaseModel):
    """Shared strictness for model-generated application material."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TailoredBullet(_StrictTailoringModel):
    """One rewritten CV bullet with mandatory addressable evidence."""

    text: str = Field(min_length=10, max_length=500)
    corpus_refs: list[CorpusReference] = Field(min_length=1, max_length=3)
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("corpus_refs")
    @classmethod
    def _require_unique_references(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("corpus_refs must not contain duplicates")
        return value


class TailoredSkill(_StrictTailoringModel):
    """One CV skill retained for the selected role and grounded in the corpus."""

    name: str = Field(min_length=2, max_length=100)
    corpus_ref: CorpusReference


class TailoringPack(_StrictTailoringModel):
    """Strict, source-linked application material for one selected job."""

    selected_job_id: str = Field(min_length=1, max_length=300)
    cover_letter: str = Field(min_length=50, max_length=5000)
    addressed_requirements: list[RequirementText] = Field(min_length=2, max_length=8)
    tailored_bullets: list[TailoredBullet] = Field(min_length=1, max_length=12)
    selected_skills: list[TailoredSkill] = Field(default_factory=list, max_length=30)
    honesty_note: str = Field(min_length=10, max_length=1500)

    @field_validator("addressed_requirements")
    @classmethod
    def _require_distinct_requirements(cls, value: list[str]) -> list[str]:
        normalized = [" ".join(item.casefold().split()) for item in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("addressed_requirements must be distinct")
        return value

    @model_validator(mode="after")
    def _enforce_pack_contract(self) -> TailoringPack:
        if len(self.cover_letter.split()) > 350:
            raise ValueError("cover_letter must contain at most 350 words")
        bullet_text = [" ".join(item.text.casefold().split()) for item in self.tailored_bullets]
        if len(bullet_text) != len(set(bullet_text)):
            raise ValueError("tailored_bullets must not contain duplicate text")
        skill_names = [" ".join(item.name.casefold().split()) for item in self.selected_skills]
        if len(skill_names) != len(set(skill_names)):
            raise ValueError("selected_skills must not contain duplicate names")
        return self


ClaimType = Literal["cv_bullet", "skill", "job_requirement", "cover_letter"]
ThresholdName = Literal["bullet", "skill", "letter"]


class FlaggedClaim(_StrictTailoringModel):
    """One generated claim the deterministic validator could not ground."""

    claim_type: ClaimType
    where: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=5000)
    reason: str = Field(min_length=1, max_length=500)
    corpus_refs: list[CorpusReference] = Field(default_factory=list, max_length=3)
    best_match_ratio: float = Field(default=0.0, ge=0.0, le=1.0)


class FabricationReport(_StrictTailoringModel):
    """Deterministic evidence report for a generated tailoring pack."""

    flags: int = Field(ge=0)
    claims_checked: int = Field(ge=0)
    flagged: list[FlaggedClaim] = Field(default_factory=list)
    thresholds: dict[ThresholdName, float]

    @field_validator("thresholds")
    @classmethod
    def _require_complete_thresholds(
        cls,
        value: dict[ThresholdName, float],
    ) -> dict[ThresholdName, float]:
        if set(value) != {"bullet", "skill", "letter"}:
            raise ValueError("thresholds must contain bullet, skill, and letter")
        if any(threshold < 0.0 or threshold > 1.0 for threshold in value.values()):
            raise ValueError("thresholds must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def _require_consistent_counts(self) -> FabricationReport:
        if self.flags != len(self.flagged):
            raise ValueError("flags must equal the number of flagged claims")
        if self.flags > self.claims_checked:
            raise ValueError("flags must not exceed claims_checked")
        return self
