"""Score each fetched job against the profile, one LLM call per batch.

The LLM returns lean ``JobScore`` objects keyed by ``job_id``; we pair each back
to its ``JobPosting`` to build a ``RankedJob``.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context

from job_scout.config import get_settings
from job_scout.graph.prompts.rank_jobs import RANK_JOBS_PROMPT
from job_scout.graph.schemas import JobPosting, JobScore, JobScores, Profile, RankedJob, ScoreBreakdown
from job_scout.graph.state import AgentState
from job_scout.grounding import ground_skill_evidence
from job_scout.llm import ensure_budget, get_chat_model
from job_scout.scoring import deterministic_components, hybrid_score

BATCH_SIZE = 5


def _render_profile(profile: Profile) -> str:
    """Format the profile as plain text for the ranking prompt."""
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
    """Format a batch of jobs as plain text for the ranking prompt."""
    return "\n\n---\n\n".join(
        f"job_id: {job.job_id}\n"
        f"title: {job.title}\n"
        f"company: {job.company}\n"
        f"location: {job.location} (remote: {job.remote})\n"
        f"description: {job.description[:1500]}"
        for job in jobs
    )


def _batches(items: list[JobPosting], size: int) -> Iterator[list[JobPosting]]:
    """Yield ``items`` in chunks of ``size``."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _batch_error(index: int, exc: Exception) -> str:
    """Return a bounded single-line batch failure for state and UI diagnostics."""
    detail = " ".join(str(exc).split())[:200]
    return f"rank_jobs: batch {index + 1} failed: {type(exc).__name__}: {detail}"


def rank_jobs(state: AgentState) -> dict:
    """Score batches concurrently, then build a deterministic ranked result."""
    settings = get_settings()
    profile = state["profile"]
    jobs = state.get("jobs", [])
    if not jobs:
        return {
            "ranked_jobs": [],
            "ranking_batch_count": 0,
            "ranking_workers": 0,
            "ranking_latency_s": 0.0,
            "ranking_failed_batches": 0,
        }

    calls = state.get("llm_calls", 0)
    batches = list(_batches(jobs, BATCH_SIZE))
    n_batches = len(batches)
    workers = min(settings.rank_max_workers, n_batches)
    ensure_budget(calls, n_batches, settings.max_llm_calls_per_run)

    model = get_chat_model(settings.scout_model, temperature=0.0).with_structured_output(JobScores)
    prompts = [
        RANK_JOBS_PROMPT.format(
            profile=_render_profile(profile),
            jobs=_render_jobs(batch),
        )
        for batch in batches
    ]
    results_by_batch: dict[int, JobScores] = {}
    errors = list(state.get("errors", []))
    failed_batches = 0
    started = time.monotonic()

    def invoke_batch(index: int) -> tuple[int, JobScores]:
        """Invoke one isolated prompt and preserve its original batch index."""
        result: JobScores = model.invoke(prompts[index])
        return index, result

    if workers == 1:
        for batch_index in range(n_batches):
            try:
                index, result = invoke_batch(batch_index)
                results_by_batch[index] = result
            except Exception as exc:  # noqa: BLE001 - retain jobs with deterministic fallback
                failed_batches += 1
                errors.append(_batch_error(batch_index, exc))
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job-rank") as executor:
            futures = {
                executor.submit(copy_context().run, invoke_batch, index): index
                for index in range(n_batches)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    completed_index, result = future.result()
                    results_by_batch[completed_index] = result
                except Exception as exc:  # noqa: BLE001 - isolate one failed batch
                    failed_batches += 1
                    errors.append(_batch_error(index, exc))

    ranking_latency_s = round(time.monotonic() - started, 3)
    calls += n_batches
    scores_by_id: dict[str, JobScore] = {}
    for index in sorted(results_by_batch):
        result = results_by_batch[index]
        allowed_ids = {job.job_id for job in batches[index]}
        for score in result.scores:
            if score.job_id in allowed_ids:
                scores_by_id[score.job_id] = score

    ranked: list[RankedJob] = []
    for job in jobs:
        assessment = scores_by_id.get(job.job_id)
        matched_evidence, gap_evidence = ground_skill_evidence(profile, job)
        components = deterministic_components(
            profile,
            job,
            grounded_skill_count=len(matched_evidence),
        )
        llm_score = assessment.fit_score if assessment else components.total
        ranked.append(
            RankedJob(
                job=job,
                fit_score=hybrid_score(components.total, llm_score),
                fit_explanation=(
                    assessment.fit_explanation
                    if assessment
                    else "The model returned no assessment for this job; the displayed fit uses deterministic signals only."
                ),
                matched_skills=[item.skill for item in matched_evidence],
                gaps=[item.skill for item in gap_evidence],
                score_breakdown=ScoreBreakdown(
                    llm=llm_score,
                    deterministic=components.total,
                    skills=components.skills,
                    role=components.role,
                    seniority=components.seniority,
                    location=components.location,
                ),
                matched_skill_evidence=matched_evidence,
                gap_evidence=gap_evidence,
            )
        )

    ranked.sort(
        key=lambda result: (
            -result.fit_score,
            -(result.score_breakdown.deterministic if result.score_breakdown else 0),
            -(result.score_breakdown.llm if result.score_breakdown else 0),
            result.job.job_id,
        )
    )
    return {
        "ranked_jobs": ranked,
        "llm_calls": calls,
        "errors": errors,
        "ranking_batch_count": n_batches,
        "ranking_workers": workers,
        "ranking_latency_s": ranking_latency_s,
        "ranking_failed_batches": failed_batches,
    }
