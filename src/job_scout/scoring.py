"""Transparent deterministic components for hybrid job-fit scoring."""

from __future__ import annotations

from dataclasses import dataclass

from job_scout.graph.schemas import JobPosting, Profile
from job_scout.grounding import ground_skill_evidence, profile_skill_group_count
from job_scout.matching import normalize_match_text
from job_scout.tools.jobs_api import location_match_rank

DETERMINISTIC_WEIGHT = 0.60
LLM_WEIGHT = 0.40

SKILL_WEIGHT = 0.40
ROLE_WEIGHT = 0.30
SENIORITY_WEIGHT = 0.15
LOCATION_WEIGHT = 0.15

_ROLE_NOISE = {
    "associate",
    "entry",
    "intern",
    "junior",
    "lead",
    "mid",
    "principal",
    "senior",
    "staff",
}
_SENIORITY_LEVELS = {"junior": 0, "mid": 1, "senior": 2, "lead": 3}


@dataclass(frozen=True)
class DeterministicComponents:
    """The four rule-based component scores and their weighted result."""

    skills: int
    role: int
    seniority: int
    location: int
    total: int


def _skill_score(
    profile: Profile,
    job: JobPosting,
    grounded_skill_count: int | None = None,
) -> int:
    """Score how many of the candidate's first-class skills occur in the job."""
    skill_count = profile_skill_group_count(profile)
    if not skill_count:
        return 50
    if grounded_skill_count is None:
        matches, _gaps = ground_skill_evidence(profile, job)
        grounded_skill_count = len(matches)
    denominator = min(skill_count, 5)
    return min(100, round(100 * grounded_skill_count / denominator))


def _role_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_match_text(value).split()
        if token not in _ROLE_NOISE
    }


def _role_score(profile: Profile, job: JobPosting) -> int:
    """Score title coverage against the candidate's preferred roles."""
    if not profile.primary_roles:
        return 50
    title_tokens = _role_tokens(job.title)
    scores = []
    for role in profile.primary_roles:
        role_tokens = _role_tokens(role)
        if role_tokens:
            scores.append(round(100 * len(role_tokens & title_tokens) / len(role_tokens)))
    return max(scores, default=50)


def _job_seniority(title: str) -> str:
    normalized = set(normalize_match_text(title).split())
    if normalized & {"chief", "director", "head", "lead", "principal", "staff"}:
        return "lead"
    if normalized & {"senior", "sr"}:
        return "senior"
    if normalized & {"intern", "internship", "junior", "jr", "graduate", "entry"}:
        return "junior"
    if normalized & {"mid", "intermediate"}:
        return "mid"
    return "unknown"


def _seniority_score(profile: Profile, job: JobPosting) -> int:
    """Score explicit job seniority; use a neutral value when it is absent."""
    candidate = profile.seniority
    offered = _job_seniority(job.title)
    if candidate == "unknown" or offered == "unknown":
        return 60
    distance = abs(_SENIORITY_LEVELS[candidate] - _SENIORITY_LEVELS[offered])
    return {0: 100, 1: 70, 2: 35, 3: 10}[distance]


def _location_score(profile: Profile, job: JobPosting) -> int:
    """Translate the location gate's best match level into a component score."""
    if not profile.locations:
        return 60
    rank = max(
        location_match_rank(
            job.location,
            location,
            None,
            job_remote=job.remote,
            remote_requested=profile.remote_ok,
        )
        for location in profile.locations
    )
    return {0: 0, 1: 60, 2: 65, 3: 90, 4: 100}[rank]


def deterministic_components(
    profile: Profile,
    job: JobPosting,
    *,
    grounded_skill_count: int | None = None,
) -> DeterministicComponents:
    """Calculate the fixed weighted rule score for one candidate and job."""
    skills = _skill_score(profile, job, grounded_skill_count)
    role = _role_score(profile, job)
    seniority = _seniority_score(profile, job)
    location = _location_score(profile, job)
    total = round(
        skills * SKILL_WEIGHT
        + role * ROLE_WEIGHT
        + seniority * SENIORITY_WEIGHT
        + location * LOCATION_WEIGHT
    )
    return DeterministicComponents(
        skills=skills,
        role=role,
        seniority=seniority,
        location=location,
        total=total,
    )


def hybrid_score(deterministic_score: int, llm_score: int) -> int:
    """Combine the rule score and LLM assessment using fixed public weights."""
    return round(deterministic_score * DETERMINISTIC_WEIGHT + llm_score * LLM_WEIGHT)
