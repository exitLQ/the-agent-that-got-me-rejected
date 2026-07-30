"""Local fpdf2 application-package rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from job_scout.corpus import CorpusItem
from job_scout.graph.schemas import (
    FabricationReport,
    FlaggedClaim,
    JobPosting,
    RankedJob,
    TailoredBullet,
    TailoringPack,
)
from job_scout.renderer import ApplicationPdfError, render_application_pdf
from job_scout.runner import TailoringResult


def _job(job_id: str = "job-1") -> RankedJob:
    return RankedJob(
        job=JobPosting(
            job_id=job_id,
            title="Data Engineer",
            company="Example GmbH",
            location="Vienna",
            description="Build Python data services.",
            source="cache",
        ),
        fit_score=85,
        fit_explanation="Strong match.",
    )


def _corpus() -> list[CorpusItem]:
    return [
        CorpusItem(
            item_id="cv-experience-001",
            text="Built Python data services for analytics.",
            kind="experience",
        ),
        CorpusItem(item_id="cv-skill-001", text="Python", kind="skill"),
    ]


def _result(*, flagged: bool = True) -> TailoringResult:
    pack = TailoringPack(
        selected_job_id="job-1",
        cover_letter=(
            "Dear hiring team,\n\n"
            "I am applying because my Python experience supports the role.\n\n"
            "Kind regards"
        ),
        addressed_requirements=["Python", "Data services"],
        tailored_bullets=[
            {
                "text": "Built reliable Python data services for analytics.",
                "corpus_refs": ["cv-experience-001"],
                "reason": "The wording stays close to the CV source.",
            }
        ],
        selected_skills=[
            {"name": "Python", "corpus_ref": "cv-skill-001"},
        ],
        honesty_note="The CV does not demonstrate every requested platform.",
    )
    claims = (
        [
            FlaggedClaim(
                claim_type="cover_letter",
                where="cover_letter:sentence:1",
                text="A claim requiring review",
                reason="No sufficiently close source was found",
                corpus_refs=["cv-experience-001"],
                best_match_ratio=0.42,
            )
        ]
        if flagged
        else []
    )
    return TailoringResult(
        selected_job_id="job-1",
        model="ollama:qwen3:8b",
        tailoring=pack,
        fabrication_report=FabricationReport(
            flags=len(claims),
            claims_checked=4,
            flagged=claims,
            thresholds={"bullet": 0.65, "skill": 0.85, "letter": 0.55},
        ),
    )


def _text(path: Path) -> str:
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_rendered_pdf_contains_draft_sources_and_every_warning(
    tmp_path,
    sample_profile,
):
    output = tmp_path / "application.pdf"

    path = render_application_pdf(
        sample_profile,
        _job(),
        _corpus(),
        _result(),
        thread_id="thread-1",
        output_path=output,
    )

    assert path == output
    assert path.read_bytes().startswith(b"%PDF")
    text = _text(path)
    assert "Application review draft" in text
    assert "never submitted automatically" in text
    assert "Cover letter draft" in text
    assert "Tailored CV draft" in text
    assert "Built reliable Python data services for analytics." in text
    assert "cv-experience-001: Built Python data services for analytics." in text
    assert "1 of 4 checked claims require review." in text
    assert "A claim requiring review" in text
    assert "No sufficiently close source was found" in " ".join(text.split())


def test_renderer_handles_unicode_and_long_unbroken_text(
    tmp_path,
    sample_profile,
):
    sample_profile.name = "Zoë Müller"
    sample_profile.raw_summary = "Responsible for APIs \u2014 " + ("verylongtoken" * 80) + " \U0001f680"

    path = render_application_pdf(
        sample_profile,
        _job(),
        _corpus(),
        _result(flagged=False),
        thread_id="thread-unicode",
        output_path=tmp_path / "unicode.pdf",
    )

    text = _text(path)
    assert "Zoë Müller" in text
    assert "Responsible for APIs -" in text
    assert len(PdfReader(path).pages) >= 1


def test_default_filename_is_stable_and_contains_no_candidate_data(sample_profile):
    first = render_application_pdf(
        sample_profile,
        _job(),
        _corpus(),
        _result(flagged=False),
        thread_id="stable-thread",
    )
    second = render_application_pdf(
        sample_profile,
        _job(),
        _corpus(),
        _result(flagged=False),
        thread_id="stable-thread",
    )

    try:
        assert first == second
        assert first.name.startswith("application-draft-")
        assert "candidate" not in first.name.casefold()
        assert "example" not in first.name.casefold()
        assert first.read_bytes().startswith(b"%PDF")
    finally:
        first.unlink(missing_ok=True)


def test_renderer_rejects_mismatched_job_before_writing(
    tmp_path,
    sample_profile,
):
    output = tmp_path / "must-not-exist.pdf"

    with pytest.raises(ApplicationPdfError, match="does not match"):
        render_application_pdf(
            sample_profile,
            _job("another-job"),
            _corpus(),
            _result(),
            thread_id="thread-1",
            output_path=output,
        )

    assert not output.exists()


def test_renderer_requires_a_tailoring_pack(tmp_path, sample_profile):
    output = tmp_path / "must-not-exist.pdf"

    with pytest.raises(ApplicationPdfError, match="No application draft"):
        render_application_pdf(
            sample_profile,
            _job(),
            _corpus(),
            TailoringResult(selected_job_id="job-1"),
            thread_id="thread-1",
            output_path=output,
        )

    assert not output.exists()


def test_renderer_adds_stable_footers_across_page_breaks(
    tmp_path,
    sample_profile,
):
    result = _result(flagged=False)
    assert result.tailoring is not None
    result.tailoring = result.tailoring.model_copy(
        update={
            "cover_letter": " ".join(["Experience"] * 350),
            "tailored_bullets": [
                TailoredBullet(
                    text=f"Evidence item {index}: " + "reliable delivery " * 20,
                    corpus_refs=["cv-experience-001"],
                    reason="The wording remains linked to the cited CV statement.",
                )
                for index in range(1, 13)
            ],
        }
    )

    path = render_application_pdf(
        sample_profile,
        _job(),
        _corpus(),
        result,
        thread_id="thread-long",
        output_path=tmp_path / "long.pdf",
    )

    reader = PdfReader(path)
    assert len(reader.pages) >= 3
    for page_number, page in enumerate(reader.pages, start=1):
        assert f"Local review draft - page {page_number}" in (page.extract_text() or "")
