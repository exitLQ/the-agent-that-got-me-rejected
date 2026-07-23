"""Deterministic and hybrid fit-scoring behavior."""

from __future__ import annotations

from job_scout.app import _job_card
from job_scout.graph.schemas import JobPosting, Profile, RankedJob, ScoreBreakdown
from job_scout.scoring import deterministic_components, hybrid_score
from tests.conftest import make_job


def test_deterministic_components_have_documented_weights(sample_profile):
    job = make_job("j1", "Data Scientist", "Acme")

    result = deterministic_components(sample_profile, job)

    assert result.skills == 50
    assert result.role == 100
    assert result.seniority == 60
    assert result.location == 100
    assert result.total == 74


def test_complete_deterministic_match_scores_one_hundred(sample_profile):
    job = make_job("j1", "Mid Data Scientist", "Acme")
    job.description = "Python, SQL, scikit-learn, and pandas are required."

    result = deterministic_components(sample_profile, job)

    assert result.skills == 100
    assert result.role == 100
    assert result.seniority == 100
    assert result.location == 100
    assert result.total == 100


def test_rule_score_limits_an_inflated_llm_assessment(sample_profile):
    job = JobPosting(
        job_id="chef",
        title="Chef",
        company="Restaurant",
        location="Berlin, Germany",
        description="Menu planning and kitchen operations.",
        source="cache",
    )

    deterministic = deterministic_components(sample_profile, job)

    assert deterministic.total == 24
    assert hybrid_score(deterministic.total, 100) == 54


def test_technical_skill_punctuation_is_normalized():
    profile = Profile(skills=["C++", "C#", ".NET", "Node.js"])
    job = JobPosting(
        job_id="platform",
        title="Platform Engineer",
        company="Acme",
        location="Remote",
        remote=True,
        description="Build services with C++, C#, .NET, and Node.js.",
        source="cache",
    )

    assert deterministic_components(profile, job).skills == 100


def test_hybrid_score_uses_fixed_sixty_forty_formula():
    assert hybrid_score(70, 90) == 78
    assert hybrid_score(90, 70) == 82


def test_duplicate_profile_skills_do_not_inflate_score():
    profile = Profile(skills=["Python", "python", "SQL"])
    job = JobPosting(
        job_id="backend",
        title="Backend Engineer",
        company="Acme",
        location="Berlin",
        description="Python services",
        source="cache",
    )

    assert deterministic_components(profile, job).skills == 50


def test_result_card_exposes_score_breakdown():
    ranked = RankedJob(
        job=make_job("j1", "Data Scientist", "Acme"),
        fit_score=76,
        fit_explanation="Good match.",
        score_breakdown=ScoreBreakdown(
            llm=80,
            deterministic=74,
            skills=50,
            role=100,
            seniority=60,
            location=100,
        ),
    )

    html = _job_card(ranked, 0)

    assert "rules 74" in html
    assert "model 80" in html
    assert "skills 50" in html
    assert 'aria-label="Hybrid fit score 76 out of 100"' in html
