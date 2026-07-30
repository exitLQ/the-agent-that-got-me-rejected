"""Strict contract tests for grounded application material."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from job_scout.graph.schemas import TailoredBullet, TailoredSkill, TailoringPack


def _valid_pack(**updates) -> TailoringPack:
    data = {
        "selected_job_id": "job-123",
        "cover_letter": (
            "I am applying for the data engineering role because my experience "
            "building reliable Python pipelines matches the stated requirements."
        ),
        "addressed_requirements": ["Python pipelines", "Reliable data systems"],
        "tailored_bullets": [
            {
                "text": "Built reliable Python pipelines for analytics workloads.",
                "corpus_refs": ["cv-experience-001"],
                "reason": "Directly supports the role's pipeline requirement.",
            }
        ],
        "selected_skills": [
            {"name": "Python", "corpus_ref": "cv-skill-001"},
        ],
        "honesty_note": "The CV does not demonstrate production Kubernetes experience.",
    }
    data.update(updates)
    return TailoringPack.model_validate(data)


def test_valid_tailoring_pack_is_strict_and_serializable():
    pack = _valid_pack()

    assert pack.selected_job_id == "job-123"
    assert pack.tailored_bullets[0].corpus_refs == ["cv-experience-001"]
    assert pack.selected_skills[0].corpus_ref == "cv-skill-001"
    assert TailoringPack.model_validate(pack.model_dump()) == pack


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (
            TailoredBullet,
            {
                "text": "A sufficiently long rewritten bullet.",
                "corpus_refs": [],
                "reason": "Grounded source.",
            },
        ),
        (
            TailoredBullet,
            {
                "text": "A sufficiently long rewritten bullet.",
                "corpus_refs": ["experience-001"],
                "reason": "Grounded source.",
            },
        ),
        (
            TailoredSkill,
            {"name": "Python", "corpus_ref": "cv-contact-001"},
        ),
    ],
)
def test_corpus_references_are_mandatory_and_typed(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_duplicate_corpus_references_are_rejected():
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        TailoredBullet(
            text="Built reliable Python data pipelines for analytics.",
            corpus_refs=["cv-experience-001", "cv-experience-001"],
            reason="The source describes this exact responsibility.",
        )


def test_cover_letter_is_limited_to_350_words():
    with pytest.raises(ValidationError, match="at most 350 words"):
        _valid_pack(cover_letter=" ".join(["word"] * 351))

    assert len(_valid_pack(cover_letter=" ".join(["word"] * 350)).cover_letter.split()) == 350


def test_at_least_two_distinct_job_requirements_are_required():
    with pytest.raises(ValidationError):
        _valid_pack(addressed_requirements=["Python"])
    with pytest.raises(ValidationError):
        _valid_pack(addressed_requirements=["Python", " "])
    with pytest.raises(ValidationError, match="must be distinct"):
        _valid_pack(addressed_requirements=["Python pipelines", " python   PIPELINES "])


def test_honesty_note_and_tailored_bullet_are_required():
    with pytest.raises(ValidationError):
        _valid_pack(honesty_note="")
    with pytest.raises(ValidationError):
        _valid_pack(tailored_bullets=[])


def test_duplicate_bullets_and_skills_are_rejected_case_insensitively():
    bullet = {
        "text": "Built reliable Python pipelines for analytics workloads.",
        "corpus_refs": ["cv-experience-001"],
        "reason": "Supports a stated requirement.",
    }
    with pytest.raises(ValidationError, match="duplicate text"):
        _valid_pack(tailored_bullets=[bullet, {**bullet, "text": bullet["text"].upper()}])

    skill = {"name": "Python", "corpus_ref": "cv-skill-001"}
    with pytest.raises(ValidationError, match="duplicate names"):
        _valid_pack(
            selected_skills=[
                skill,
                {"name": " python ", "corpus_ref": "cv-skill-002"},
            ]
        )


def test_unknown_model_fields_are_rejected():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TailoredSkill.model_validate(
            {
                "name": "Python",
                "corpus_ref": "cv-skill-001",
                "unsupported_claim": "invented",
            }
        )
