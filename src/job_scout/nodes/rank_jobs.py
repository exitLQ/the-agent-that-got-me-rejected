"""Node: score each job against the profile, one LLM call per batch of 5.

The LLM returns a lean score object keyed by ``job_id`` (not the whole posting),
and we pair each score back to its ``JobPosting`` to build ``RankedJob``. The
ranking prompt is deliberately first-draft (Phase 3 optimizes it).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from job_scout.config import get_settings
from job_scout.llm import ensure_budget, get_chat_model
from job_scout.prompts.rank_jobs import RANK_JOBS_PROMPT
from job_scout.schemas import AgentState, JobPosting, Profile, RankedJob

BATCH_SIZE = 5


class _JobScore(BaseModel):
    """Lean per-job score the LLM returns (paired back to the posting by id)."""

    job_id: str
    fit_score: int = Field(ge=0, le=100)
    fit_explanation: str
    matched_skills: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class _JobScores(BaseModel):
    scores: list[_JobScore]


def _render_profile(profile: Profile) -> str:
    return (
        f"Name: {profile.name}\n"
        f"Seniority: {profile.seniority}\n"
        f"Roles: {', '.join(profile.primary_roles)}\n"
        f"Skills: {', '.join(profile.skills)}\n"
        f"Years experience: {profile.years_experience}\n"
        f"Locations: {', '.join(profile.locations)}\n"
        f"Remote ok: {profile.remote_ok}"
    )


def _render_jobs(jobs: list[JobPosting]) -> str:
    blocks = []
    for job in jobs:
        blocks.append(
            f"job_id: {job.job_id}\n"
            f"title: {job.title}\n"
            f"company: {job.company}\n"
            f"location: {job.location} (remote: {job.remote})\n"
            f"description: {job.description[:1500]}"
        )
    return "\n\n---\n\n".join(blocks)


def _batches(items: list[JobPosting], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def rank_jobs(state: AgentState) -> dict:
    settings = get_settings()
    profile = state["profile"]
    jobs = state.get("jobs", [])
    if not jobs:
        return {"ranked_jobs": []}

    by_id = {job.job_id: job for job in jobs}
    calls = state.get("llm_calls", 0)
    n_batches = (len(jobs) + BATCH_SIZE - 1) // BATCH_SIZE
    ensure_budget(calls, n_batches, settings.max_llm_calls_per_run)

    model = get_chat_model(settings.scout_model, temperature=0.0).with_structured_output(_JobScores)
    ranked: list[RankedJob] = []
    for batch in _batches(jobs, BATCH_SIZE):
        prompt = RANK_JOBS_PROMPT.format(profile=_render_profile(profile), jobs=_render_jobs(batch))
        result: _JobScores = model.invoke(prompt)
        calls += 1
        for score in result.scores:
            job = by_id.get(score.job_id)
            if job is None:
                continue  # model referenced a job id not in this batch — skip
            ranked.append(
                RankedJob(
                    job=job,
                    fit_score=score.fit_score,
                    fit_explanation=score.fit_explanation,
                    matched_skills=score.matched_skills,
                    gaps=score.gaps,
                )
            )

    ranked.sort(key=lambda r: r.fit_score, reverse=True)
    return {"ranked_jobs": ranked, "llm_calls": calls}
