"""Deterministic fabrication checks for generated application material."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from job_scout.config import Settings
from job_scout.corpus import CorpusItem
from job_scout.graph.schemas import TailoringPack
from job_scout.validation import validate_pack


def _corpus() -> list[CorpusItem]:
    return [
        CorpusItem(
            item_id="cv-experience-001",
            text="Built Python pipelines processing 10 million records per day.",
            kind="experience",
        ),
        CorpusItem(
            item_id="cv-experience-002",
            text="Operated reliable analytics services on AWS.",
            kind="experience",
        ),
        CorpusItem(item_id="cv-skill-001", text="Python", kind="skill"),
    ]


def _pack(**updates) -> TailoringPack:
    data = {
        "selected_job_id": "job-1",
        "cover_letter": (
            "Dear hiring team,\n"
            "I built Python pipelines processing 10 million records per day. "
            "I would welcome the opportunity to contribute to your team.\n"
            "Kind regards"
        ),
        "addressed_requirements": ["Python", "Reliable services"],
        "tailored_bullets": [
            {
                "text": "Built Python pipelines processing 10 million records per day.",
                "corpus_refs": ["cv-experience-001"],
                "reason": "This is supported directly by the cited CV item.",
            }
        ],
        "selected_skills": [
            {"name": "Python", "corpus_ref": "cv-skill-001"},
        ],
        "honesty_note": "The CV does not demonstrate every requested platform.",
    }
    data.update(updates)
    return TailoringPack.model_validate(data)


def _job_context(*extra: str) -> list[str]:
    return ["Python", "Reliable services", *extra]


def test_grounded_pack_has_no_flags_and_records_thresholds():
    report = validate_pack(_pack(), _corpus(), job_context=_job_context())

    assert report.flags == 0
    assert report.claims_checked == 5
    assert report.flagged == []
    assert report.thresholds == {
        "bullet": 0.65,
        "skill": 0.85,
        "letter": 0.55,
    }


def test_missing_references_are_flagged_without_crashing():
    pack = _pack(
        tailored_bullets=[
            {
                "text": "Built Python pipelines processing 10 million records per day.",
                "corpus_refs": ["cv-experience-999"],
                "reason": "The generated reference has the right shape but does not exist.",
            }
        ],
        selected_skills=[
            {"name": "Python", "corpus_ref": "cv-skill-999"},
        ],
    )

    report = validate_pack(pack, _corpus(), job_context=_job_context())

    assert report.flags == 2
    assert report.claims_checked == 5
    assert report.flagged[0].claim_type == "cv_bullet"
    assert "cv-experience-999" in report.flagged[0].reason
    assert report.flagged[1].claim_type == "skill"
    assert "cv-skill-999" in report.flagged[1].reason


def test_drifted_bullet_and_unsupported_skill_are_flagged():
    pack = _pack(
        tailored_bullets=[
            {
                "text": "Led a global Kubernetes migration that doubled annual revenue.",
                "corpus_refs": ["cv-experience-001"],
                "reason": "This intentionally overstates the cited source.",
            }
        ],
        selected_skills=[
            {"name": "Kubernetes", "corpus_ref": "cv-skill-001"},
        ],
    )

    report = validate_pack(pack, _corpus(), job_context=_job_context())

    assert [flag.claim_type for flag in report.flagged] == ["cv_bullet", "skill"]
    assert all(flag.best_match_ratio < 0.65 for flag in report.flagged)


def test_multi_source_bullet_can_be_grounded_by_combined_citations():
    pack = _pack(
        tailored_bullets=[
            {
                "text": (
                    "Built Python pipelines processing 10 million records per day. "
                    "Operated reliable analytics services on AWS."
                ),
                "corpus_refs": ["cv-experience-001", "cv-experience-002"],
                "reason": "Both source statements are retained without new facts.",
            }
        ]
    )

    report = validate_pack(pack, _corpus(), job_context=_job_context())

    assert not any(flag.claim_type == "cv_bullet" for flag in report.flagged)


def test_addressed_requirement_must_appear_in_selected_job_context():
    pack = _pack(
        addressed_requirements=["Python", "Quantum computing certification"],
    )

    report = validate_pack(pack, _corpus(), job_context=_job_context())

    flag = next(flag for flag in report.flagged if flag.claim_type == "job_requirement")
    assert flag.where == "job_requirement:2"
    assert "selected job" in flag.reason


def test_first_person_claim_cannot_be_grounded_only_by_job_text():
    sentence = "I led a Kubernetes platform serving 50 million users at Example GmbH."
    pack = _pack(cover_letter=f"Dear team,\n{sentence}\nKind regards")

    report = validate_pack(
        pack,
        _corpus(),
        job_context=_job_context(sentence, "Example GmbH", "Kubernetes"),
    )

    flag = next(flag for flag in report.flagged if flag.claim_type == "cover_letter")
    assert flag.text == sentence
    assert "candidate corpus" in flag.reason


def test_german_first_person_claim_also_requires_candidate_evidence():
    sentence = "Ich habe eine Kubernetes Plattform für 50 Millionen Nutzer geleitet."
    pack = _pack(cover_letter=f"Sehr geehrte Damen und Herren,\n{sentence}\nBeste Grüße")

    report = validate_pack(
        pack,
        _corpus(),
        job_context=_job_context(sentence, "Kubernetes"),
    )

    flag = next(flag for flag in report.flagged if flag.claim_type == "cover_letter")
    assert "candidate corpus" in flag.reason


def test_non_candidate_job_fact_can_use_job_context():
    sentence = "Example GmbH operates an AWS analytics platform in Berlin."
    pack = _pack(cover_letter=f"Dear team,\n{sentence}\nKind regards")

    report = validate_pack(pack, _corpus(), job_context=_job_context(sentence))

    assert not any(flag.claim_type == "cover_letter" for flag in report.flagged)


def test_validation_is_deterministic():
    first = validate_pack(_pack(), _corpus(), job_context=_job_context()).model_dump()
    second = validate_pack(_pack(), _corpus(), job_context=_job_context()).model_dump()

    assert first == second


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SCOUT_FAB_BULLET_RATIO", -0.01),
        ("SCOUT_FAB_SKILL_RATIO", 1.01),
        ("SCOUT_FAB_LETTER_RATIO", -1),
    ],
)
def test_threshold_settings_reject_values_outside_zero_to_one(name, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{name: value})
