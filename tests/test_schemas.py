"""Schema invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from job_scout.graph.schemas import (
    JobPosting,
    QueryReformulation,
    RankedJob,
    ScoreBreakdown,
    SkillEvidence,
)
from tests.conftest import make_job


def test_ranked_job_score_bounds():
    job = make_job("j1", "Data Scientist", "Acme")
    RankedJob(job=job, fit_score=0, fit_explanation="x")
    RankedJob(job=job, fit_score=100, fit_explanation="x")
    with pytest.raises(ValidationError):
        RankedJob(job=job, fit_score=101, fit_explanation="x")
    with pytest.raises(ValidationError):
        RankedJob(job=job, fit_score=-1, fit_explanation="x")


def test_job_posting_source_literal():
    JobPosting(job_id="1", title="t", company="c", location="l", source="adzuna")
    with pytest.raises(ValidationError):
        JobPosting(job_id="1", title="t", company="c", location="l", source="linkedin")


def test_score_breakdown_bounds():
    ScoreBreakdown(llm=0, deterministic=100, skills=50, role=50, seniority=50, location=50)
    with pytest.raises(ValidationError):
        ScoreBreakdown(llm=101, deterministic=100, skills=50, role=50, seniority=50, location=50)


def test_skill_evidence_requires_both_provenance_fields():
    SkillEvidence(
        skill="Python",
        profile_evidence="profile.skills: Python",
        job_evidence="description: Python required.",
    )
    with pytest.raises(ValidationError):
        SkillEvidence(
            skill="Python",
            profile_evidence="profile.skills: Python",
        )


def test_query_reformulation_bounds():
    QueryReformulation(
        attempt=1,
        previous_query="data scientist",
        query="data analyst",
        strategy="model",
        reason="novel",
        jobs_seen=3,
        good_jobs=1,
        best_score=70,
    )
    with pytest.raises(ValidationError):
        QueryReformulation(
            attempt=0,
            previous_query="data scientist",
            query="data analyst",
            strategy="fallback",
            reason="invalid",
            jobs_seen=3,
            good_jobs=1,
            best_score=70,
        )
