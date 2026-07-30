"""Offline deterministic evaluation contracts, metrics, and privacy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from job_scout.evals import (
    EvaluationInterfaceError,
    LocalEvaluationDataset,
    evaluate_dataset,
)
from scripts.run_local_evals import run

FIXTURE = Path("data/evaluation/local_fixture.json")


def _dataset() -> LocalEvaluationDataset:
    return LocalEvaluationDataset.model_validate_json(
        FIXTURE.read_text(encoding="utf-8")
    )


def test_profile_accuracy_normalizes_case_whitespace_and_list_order():
    report = evaluate_dataset(_dataset())

    assert report.summary.profile_field_accuracy == 1.0
    assert report.summary.matched_profile_fields == 8
    assert report.summary.total_profile_fields == 8
    assert report.profile_cases[0].mismatched_fields == []


def test_profile_accuracy_reports_field_names_not_private_values():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["profile_cases"][0]["actual"]["years_experience"] = 11
    dataset = LocalEvaluationDataset.model_validate(raw)

    result = evaluate_dataset(dataset).profile_cases[0]

    assert result.field_accuracy == 0.875
    assert result.mismatched_fields == ["years_experience"]
    serialized = result.model_dump_json()
    assert "Test Candidate" not in serialized
    assert "Vienna" not in serialized


def test_unverified_profile_labels_are_rejected():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["profile_cases"][0]["human_verified"] = False

    with pytest.raises(ValidationError):
        LocalEvaluationDataset.model_validate(raw)


def test_duplicate_case_ids_are_rejected():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["tailoring_cases"][0]["case_id"] = raw["profile_cases"][0]["case_id"]

    with pytest.raises(ValidationError, match="case_id values must be unique"):
        LocalEvaluationDataset.model_validate(raw)


def test_tailoring_metrics_reuse_production_validator():
    report = evaluate_dataset(_dataset())
    case = report.tailoring_cases[0]

    assert case.fabrication_flags == 2
    assert case.claims_checked == 4
    assert case.fabrication_rate == 0.5
    assert case.grounded_claim_rate == 0.5
    assert case.citations_resolved == 2
    assert case.citations_total == 2
    assert case.citation_resolution_rate == 1.0
    assert case.cover_letter_within_limit is True
    assert case.warning_counts == {"cv_bullet": 1, "skill": 1}


def test_empty_dataset_uses_null_for_metrics_without_a_denominator():
    report = evaluate_dataset(LocalEvaluationDataset())

    assert report.summary.profile_field_accuracy is None
    assert report.summary.fabrication_rate is None
    assert report.summary.grounded_claim_rate is None
    assert report.summary.citation_resolution_rate is None
    assert report.summary.cover_letter_compliance_rate is None


def test_report_is_stable_and_contains_no_candidate_or_corpus_text():
    first = evaluate_dataset(_dataset()).model_dump_json()
    second = evaluate_dataset(_dataset()).model_dump_json()

    assert first == second
    assert "Test Candidate" not in first
    assert "Built Python data services" not in first
    assert "global Kubernetes migration" not in first
    assert "dataset_sha256" in first


def test_cli_runner_writes_byte_stable_privacy_minimized_report(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    first = run(FIXTURE, first_path)
    second = run(FIXTURE, second_path)

    assert first == second
    assert first_path.read_bytes() == second_path.read_bytes()
    output = first_path.read_text(encoding="utf-8")
    assert "Test Candidate" not in output
    assert "Built Python data services" not in output


def test_cli_runner_refuses_to_overwrite_its_input():
    with pytest.raises(EvaluationInterfaceError, match="must not overwrite"):
        run(FIXTURE, FIXTURE)
