"""Offline, deterministic evaluation for profiles and tailoring packages.

The evaluator separates mechanically verifiable checks from subjective
judgments. It accepts only explicitly human-verified profile labels, reuses the
production fabrication validator, and emits aggregate metadata without copying
profile values, corpus text, generated prose, or warning text into the report.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from job_scout.corpus import CorpusItem
from job_scout.graph.schemas import Profile, TailoringPack
from job_scout.validation import validate_pack

ProfileField = Literal[
    "name",
    "seniority",
    "primary_roles",
    "skills",
    "years_experience",
    "locations",
    "languages",
    "remote_ok",
]
PROFILE_FIELDS: tuple[ProfileField, ...] = (
    "name",
    "seniority",
    "primary_roles",
    "skills",
    "years_experience",
    "locations",
    "languages",
    "remote_ok",
)
_SPACE = re.compile(r"\s+")


class _StrictEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileEvaluationCase(_StrictEvaluationModel):
    """One actual profile compared with labels owned and verified by a human."""

    case_id: str = Field(min_length=1, max_length=200)
    human_verified: Literal[True]
    expected: Profile
    actual: Profile
    fields: list[ProfileField] = Field(default_factory=lambda: list(PROFILE_FIELDS))

    @field_validator("fields")
    @classmethod
    def _unique_fields(cls, value: list[ProfileField]) -> list[ProfileField]:
        if not value:
            raise ValueError("fields must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("fields must not contain duplicates")
        return value


class TailoringEvaluationCase(_StrictEvaluationModel):
    """One strict tailoring pack plus the exact local evidence used to check it."""

    case_id: str = Field(min_length=1, max_length=200)
    pack: TailoringPack
    corpus: list[CorpusItem] = Field(min_length=1)
    job_context: list[str] = Field(min_length=1)


class LocalEvaluationDataset(_StrictEvaluationModel):
    """Versioned input accepted by the local deterministic evaluator."""

    schema_version: Literal[1] = 1
    profile_cases: list[ProfileEvaluationCase] = Field(default_factory=list)
    tailoring_cases: list[TailoringEvaluationCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_case_ids(self) -> LocalEvaluationDataset:
        case_ids = [
            *(case.case_id for case in self.profile_cases),
            *(case.case_id for case in self.tailoring_cases),
        ]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique across the dataset")
        return self


class ProfileCaseResult(_StrictEvaluationModel):
    case_id: str
    matched_fields: int = Field(ge=0)
    total_fields: int = Field(ge=1)
    field_accuracy: float = Field(ge=0.0, le=1.0)
    mismatched_fields: list[ProfileField]


class TailoringCaseResult(_StrictEvaluationModel):
    case_id: str
    claims_checked: int = Field(ge=0)
    fabrication_flags: int = Field(ge=0)
    fabrication_rate: float = Field(ge=0.0, le=1.0)
    grounded_claim_rate: float = Field(ge=0.0, le=1.0)
    citations_resolved: int = Field(ge=0)
    citations_total: int = Field(ge=0)
    citation_resolution_rate: float = Field(ge=0.0, le=1.0)
    cover_letter_words: int = Field(ge=0)
    cover_letter_within_limit: bool
    warning_counts: dict[str, int]
    thresholds: dict[str, float]


class EvaluationSummary(_StrictEvaluationModel):
    profile_cases: int = Field(ge=0)
    tailoring_cases: int = Field(ge=0)
    matched_profile_fields: int = Field(ge=0)
    total_profile_fields: int = Field(ge=0)
    profile_field_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    fabrication_flags: int = Field(ge=0)
    claims_checked: int = Field(ge=0)
    fabrication_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    grounded_claim_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    citations_resolved: int = Field(ge=0)
    citations_total: int = Field(ge=0)
    citation_resolution_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    cover_letters_within_limit: int = Field(ge=0)
    cover_letter_compliance_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )


class LocalEvaluationReport(_StrictEvaluationModel):
    """Stable, privacy-minimized output containing no candidate prose."""

    schema_version: Literal[1] = 1
    evaluator: Literal["local-deterministic-v1"] = "local-deterministic-v1"
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: EvaluationSummary
    profile_cases: list[ProfileCaseResult]
    tailoring_cases: list[TailoringCaseResult]


def _normalized(value: object) -> object:
    if isinstance(value, str):
        return _SPACE.sub(" ", value.casefold()).strip()
    if isinstance(value, list):
        return tuple(sorted(_normalized(item) for item in value))
    if isinstance(value, float):
        return round(value, 9)
    return value


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _dataset_digest(dataset: LocalEvaluationDataset) -> str:
    canonical = json.dumps(
        dataset.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _evaluate_profile(case: ProfileEvaluationCase) -> ProfileCaseResult:
    mismatches = [
        field
        for field in case.fields
        if _normalized(getattr(case.expected, field))
        != _normalized(getattr(case.actual, field))
    ]
    total = len(case.fields)
    matched = total - len(mismatches)
    return ProfileCaseResult(
        case_id=case.case_id,
        matched_fields=matched,
        total_fields=total,
        field_accuracy=round(matched / total, 6),
        mismatched_fields=mismatches,
    )


def _evaluate_tailoring(case: TailoringEvaluationCase) -> TailoringCaseResult:
    report = validate_pack(
        case.pack,
        case.corpus,
        job_context=case.job_context,
    )
    available = {item.item_id for item in case.corpus}
    citations = [
        reference
        for bullet in case.pack.tailored_bullets
        for reference in bullet.corpus_refs
    ]
    citations.extend(skill.corpus_ref for skill in case.pack.selected_skills)
    resolved = sum(reference in available for reference in citations)
    fabrication_rate = _rate(report.flags, report.claims_checked) or 0.0
    citation_rate = _rate(resolved, len(citations))
    warning_counts = Counter(flag.claim_type for flag in report.flagged)
    words = len(case.pack.cover_letter.split())
    return TailoringCaseResult(
        case_id=case.case_id,
        claims_checked=report.claims_checked,
        fabrication_flags=report.flags,
        fabrication_rate=fabrication_rate,
        grounded_claim_rate=round(1.0 - fabrication_rate, 6),
        citations_resolved=resolved,
        citations_total=len(citations),
        citation_resolution_rate=citation_rate if citation_rate is not None else 1.0,
        cover_letter_words=words,
        cover_letter_within_limit=words <= 350,
        warning_counts=dict(sorted(warning_counts.items())),
        thresholds=report.thresholds,
    )


def evaluate_dataset(dataset: LocalEvaluationDataset) -> LocalEvaluationReport:
    """Evaluate a parsed dataset without model, network, trace, or file access."""
    profile_results = [_evaluate_profile(case) for case in dataset.profile_cases]
    tailoring_results = [
        _evaluate_tailoring(case) for case in dataset.tailoring_cases
    ]

    matched_fields = sum(case.matched_fields for case in profile_results)
    total_fields = sum(case.total_fields for case in profile_results)
    flags = sum(case.fabrication_flags for case in tailoring_results)
    claims = sum(case.claims_checked for case in tailoring_results)
    citations_resolved = sum(case.citations_resolved for case in tailoring_results)
    citations_total = sum(case.citations_total for case in tailoring_results)
    compliant_letters = sum(
        case.cover_letter_within_limit for case in tailoring_results
    )
    fabrication_rate = _rate(flags, claims)

    return LocalEvaluationReport(
        dataset_sha256=_dataset_digest(dataset),
        summary=EvaluationSummary(
            profile_cases=len(profile_results),
            tailoring_cases=len(tailoring_results),
            matched_profile_fields=matched_fields,
            total_profile_fields=total_fields,
            profile_field_accuracy=_rate(matched_fields, total_fields),
            fabrication_flags=flags,
            claims_checked=claims,
            fabrication_rate=fabrication_rate,
            grounded_claim_rate=(
                round(1.0 - fabrication_rate, 6)
                if fabrication_rate is not None
                else None
            ),
            citations_resolved=citations_resolved,
            citations_total=citations_total,
            citation_resolution_rate=_rate(citations_resolved, citations_total),
            cover_letters_within_limit=compliant_letters,
            cover_letter_compliance_rate=_rate(
                compliant_letters,
                len(tailoring_results),
            ),
        ),
        profile_cases=profile_results,
        tailoring_cases=tailoring_results,
    )
