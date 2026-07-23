"""Evidence grounding for displayed skill matches and gaps."""

from __future__ import annotations

from job_scout.graph.schemas import JobPosting, Profile
from job_scout.grounding import ground_skill_evidence


def _job(description: str, *, title: str = "Platform Engineer", tags: list[str] | None = None) -> JobPosting:
    return JobPosting(
        job_id="job",
        title=title,
        company="Acme",
        location="Berlin",
        description=description,
        tags=tags or [],
        source="cache",
    )


def test_matches_require_both_profile_and_job_evidence():
    profile = Profile(skills=["Python", "SQL", "Pandas"])
    job = _job("Strong Python and SQL skills are required.")

    matches, gaps = ground_skill_evidence(profile, job)

    assert [item.skill for item in matches] == ["Python", "SQL"]
    assert gaps == []
    assert matches[0].profile_evidence == "profile.skills: Python"
    assert matches[0].job_evidence.startswith("description:")


def test_aliases_resolve_to_the_profile_spelling():
    profile = Profile(skills=["ML", "Amazon Web Services"])
    job = _job("Machine learning experience is required. We deploy on AWS.")

    matches, _ = ground_skill_evidence(profile, job)

    assert [item.skill for item in matches] == ["ML", "Amazon Web Services"]


def test_required_job_skill_absent_from_profile_becomes_grounded_gap():
    profile = Profile(skills=["Python"])
    job = _job("AWS and Kubernetes experience are required.")

    _, gaps = ground_skill_evidence(profile, job)

    assert [item.skill for item in gaps] == ["AWS", "Kubernetes"]
    assert all(item.profile_evidence == "not present in profile.skills" for item in gaps)
    assert all(item.job_evidence.startswith("description:") for item in gaps)


def test_optional_or_negated_skill_is_not_a_gap():
    profile = Profile(skills=["Python"])
    job = _job(
        "Kubernetes is optional. AWS experience is not required. "
        "No Terraform experience is required. Python skills are required."
    )

    _, gaps = ground_skill_evidence(profile, job)

    assert gaps == []


def test_title_and_tag_are_direct_requirement_evidence():
    profile = Profile(skills=["Python"])
    job = _job("Build reliable systems.", title="Kubernetes Engineer", tags=["Terraform"])

    _, gaps = ground_skill_evidence(profile, job)

    assert [item.skill for item in gaps] == ["Kubernetes", "Terraform"]
    assert gaps[0].job_evidence == "title: Kubernetes Engineer"
    assert gaps[1].job_evidence == "tag: Terraform"


def test_javascript_does_not_create_a_java_match():
    profile = Profile(skills=["Java"])
    job = _job("JavaScript experience is required.")

    matches, _ = ground_skill_evidence(profile, job)

    assert matches == []
