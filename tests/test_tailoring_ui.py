"""Fourth-step Gradio flow, consent boundary, and safe rendering."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import job_scout.app as app
from job_scout.corpus import CorpusItem
from job_scout.graph.schemas import (
    FabricationReport,
    FlaggedClaim,
    JobPosting,
    RankedJob,
    TailoringPack,
)
from job_scout.runner import RunResult, TailoringResult


def _ranked() -> RankedJob:
    return RankedJob(
        job=JobPosting(
            job_id="job-1",
            title="Data Engineer",
            company="Example GmbH",
            location="Vienna",
            description="Build Python data services.",
            tags=["Python"],
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


def _pack() -> TailoringPack:
    return TailoringPack(
        selected_job_id="job-1",
        cover_letter=(
            "I am applying for this data engineering role because my Python "
            "experience supports the stated requirements."
        ),
        addressed_requirements=["Python", "Data services"],
        tailored_bullets=[
            {
                "text": "Built <reliable> Python data services for analytics.",
                "corpus_refs": ["cv-experience-001"],
                "reason": "The rewrite remains close to the cited source.",
            }
        ],
        selected_skills=[
            {"name": "Python", "corpus_ref": "cv-skill-001"},
        ],
        honesty_note="The CV does not demonstrate every requested platform.",
    )


def _result(*, flagged: bool = False) -> TailoringResult:
    flags = []
    if flagged:
        flags = [
            FlaggedClaim(
                claim_type="cv_bullet",
                where="cv_bullet:1",
                text="<unsafe generated claim>",
                reason="rewrite drifted too far",
                corpus_refs=["cv-experience-001"],
                best_match_ratio=0.321,
            )
        ]
    return TailoringResult(
        selected_job_id="job-1",
        model="ollama:qwen3:8b",
        tailoring=_pack(),
        fabrication_report=FabricationReport(
            flags=len(flags),
            claims_checked=4,
            flagged=flags,
            thresholds={"bullet": 0.65, "skill": 0.85, "letter": 0.55},
        ),
        latency_s=0.25,
    )


def test_stepper_has_four_steps():
    html = app._stepper(4)

    assert html.count('class="js-step ') == 4
    assert "Application" in html
    assert "js-step-active" in html


def test_tailoring_disclosure_distinguishes_local_and_external_models():
    local = app._tailor_transfer_html("ollama:qwen3:8b")
    cloud = app._tailor_transfer_html("anthropic:claude-sonnet-4-6")

    assert "Local tailoring model" in local
    assert "local Ollama" in local
    assert "External tailoring model" in cloud
    assert "sent to anthropic" in cloud
    assert "Private tracker notes" in cloud


def test_tailoring_render_shows_sources_and_escapes_generated_text():
    html = app._tailoring_html(_result(flagged=True), _corpus())

    assert "1 of 4 checked claims require review" in html
    assert "rewrite drifted too far" in html
    assert "best ratio 0.321" in html
    assert "Built Python data services for analytics." in html
    assert "cv-experience-001" in html
    assert "Honesty note" in html
    assert "<unsafe generated claim>" not in html
    assert "&lt;unsafe generated claim&gt;" in html
    assert "<reliable>" not in html
    assert "&lt;reliable&gt;" in html


def test_clean_report_still_requires_human_review():
    html = app._tailoring_html(_result(), _corpus())

    assert "No claims were flagged" in html
    assert "not a guarantee of truth" in html


def test_tailoring_requires_confirmation_before_validation_or_model_call(
    monkeypatch,
    sample_profile,
):
    monkeypatch.setattr(
        app,
        "validate_model_configuration",
        lambda model: (_ for _ in ()).throw(AssertionError("model validation ran")),
    )
    monkeypatch.setattr(
        app,
        "stream_tailoring",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("tailoring ran")),
    )

    events = list(
        app.on_tailor(
            sample_profile,
            [_ranked()],
            _corpus(),
            "job-1",
            False,
            "thread-1",
        )
    )

    assert len(events) == 1
    assert events[0][0]["visible"] is True
    assert events[0][1]["visible"] is False
    assert "Confirm this specific tailoring run" in events[0][9]


def test_search_does_not_preselect_tailoring_job(monkeypatch, sample_profile):
    result = RunResult(
        profile=sample_profile,
        model="ollama:qwen3:8b",
        ranked_jobs=[_ranked()],
    )
    monkeypatch.setattr(
        app,
        "stream_search",
        lambda *args, **kwargs: iter([("result", result)]),
    )

    final = list(
        app.on_find(
            sample_profile,
            "thread-1",
            "ollama:qwen3:8b",
        )
    )[-1]

    assert final[4]["value"] == "job-1"
    assert final[6]["value"] is None
    assert final[6]["choices"] == [
        ("Data Engineer — Example GmbH", "job-1"),
    ]
    assert final[7] is False


def test_unknown_job_is_rejected_before_model_validation(monkeypatch, sample_profile):
    monkeypatch.setattr(
        app,
        "validate_model_configuration",
        lambda model: (_ for _ in ()).throw(AssertionError("model validation ran")),
    )

    events = list(
        app.on_tailor(
            sample_profile,
            [_ranked()],
            _corpus(),
            "missing",
            True,
            "thread-1",
        )
    )

    assert len(events) == 1
    assert "no longer available" in events[0][9]


def test_missing_corpus_is_rejected_before_model_validation(monkeypatch, sample_profile):
    monkeypatch.setattr(
        app,
        "validate_model_configuration",
        lambda model: (_ for _ in ()).throw(AssertionError("model validation ran")),
    )

    events = list(
        app.on_tailor(
            sample_profile,
            [_ranked()],
            [],
            "job-1",
            True,
            "thread-1",
        )
    )

    assert len(events) == 1
    assert "temporary CV corpus is unavailable" in events[0][9]


def test_blocked_tailoring_model_never_starts_runner(monkeypatch, sample_profile):
    monkeypatch.setattr(
        app,
        "get_settings",
        lambda: SimpleNamespace(scout_tailor_model="anthropic:blocked"),
    )
    monkeypatch.setattr(
        app,
        "validate_model_configuration",
        lambda model: (_ for _ in ()).throw(app.ModelConfigurationError("blocked")),
    )
    monkeypatch.setattr(
        app,
        "stream_tailoring",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("tailoring ran")),
    )

    events = list(
        app.on_tailor(
            sample_profile,
            [_ranked()],
            _corpus(),
            "job-1",
            True,
            "thread-1",
        )
    )

    assert len(events) == 1
    assert "Tailoring model is not ready: blocked" in events[0][9]


def test_confirmed_tailoring_streams_result_with_explicit_session_data(
    monkeypatch,
    sample_profile,
):
    captured = {}
    result = _result(flagged=True)
    monkeypatch.setattr(
        app,
        "get_settings",
        lambda: SimpleNamespace(
            scout_tailor_model="ollama:qwen3:8b",
            has_opik=False,
        ),
    )
    monkeypatch.setattr(
        app,
        "validate_model_configuration",
        lambda model: captured.setdefault("validated_model", model),
    )
    monkeypatch.setattr(
        app,
        "render_application_pdf",
        lambda *args, **kwargs: Path("application-review.pdf"),
    )

    def fake_stream(profile, ranked_jobs, corpus, **kwargs):
        captured["profile"] = profile
        captured["ranked_jobs"] = ranked_jobs
        captured["corpus"] = corpus
        captured["kwargs"] = kwargs
        yield "status", "checking claims"
        yield "result", result

    monkeypatch.setattr(app, "stream_tailoring", fake_stream)

    events = list(
        app.on_tailor(
            sample_profile.model_dump(),
            [_ranked().model_dump()],
            [item.model_dump() for item in _corpus()],
            "job-1",
            True,
            "thread-1",
        )
    )

    final = events[-1]
    assert final[0]["visible"] is False
    assert final[1]["visible"] is True
    assert "require review" in final[2]
    assert final[3] == _pack().cover_letter
    assert final[4]["visible"] is True
    assert final[4]["value"] == "application-review.pdf"
    assert final[5] == ""
    assert "validator warnings: 1" in final[6]
    assert final[7] is result
    assert final[8] == "application-review.pdf"
    assert captured["validated_model"] == "ollama:qwen3:8b"
    assert captured["profile"] == sample_profile
    assert captured["ranked_jobs"][0].job.job_id == "job-1"
    assert captured["corpus"] == _corpus()
    assert captured["kwargs"] == {
        "selected_job_id": "job-1",
        "thread_id": "thread-1",
        "tags": ["phase-2", "ui", "tailor"],
        "model_name": "ollama:qwen3:8b",
    }


def test_tailoring_callback_has_no_tracker_note_input():
    assert "notes" not in inspect.signature(app.on_tailor).parameters


def test_job_change_and_back_navigation_invalidate_confirmation():
    assert app.on_tailor_job_change() == (False, "")
    back = app.back_to_jobs()
    assert back[0]["visible"] is True
    assert back[1]["visible"] is False
    assert back[2:] == (False, "")


def test_reset_clears_tailoring_state_and_creates_fresh_thread():
    first = app.reset()
    second = app.reset()

    assert len(first) == 24
    assert first[3]["visible"] is False
    assert first[13]["choices"] == []
    assert first[14] is False
    assert first[16:18] == ("", "")
    assert first[18]["visible"] is False
    assert first[19:23] == ("", "", None, None)
    assert first[23] != second[23]


def test_reset_deletes_the_current_transient_pdf(monkeypatch):
    deleted = []
    monkeypatch.setattr(
        app,
        "delete_temporary_upload",
        lambda path: deleted.append(path) or True,
    )

    reset_values = app.reset("temporary-application.pdf")

    assert deleted == ["temporary-application.pdf"]
    assert reset_values[18]["visible"] is False
    assert reset_values[22] is None


def test_pdf_failure_does_not_discard_application_text(
    monkeypatch,
    sample_profile,
):
    result = _result()
    monkeypatch.setattr(
        app,
        "get_settings",
        lambda: SimpleNamespace(
            scout_tailor_model="ollama:qwen3:8b",
            has_opik=False,
        ),
    )
    monkeypatch.setattr(app, "validate_model_configuration", lambda model: None)
    monkeypatch.setattr(
        app,
        "stream_tailoring",
        lambda *args, **kwargs: iter([("result", result)]),
    )
    monkeypatch.setattr(
        app,
        "render_application_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            app.ApplicationPdfError("render failed")
        ),
    )

    final = list(
        app.on_tailor(
            sample_profile,
            [_ranked()],
            _corpus(),
            "job-1",
            True,
            "thread-1",
        )
    )[-1]

    assert final[1]["visible"] is True
    assert final[3] == _pack().cover_letter
    assert final[4]["visible"] is False
    assert "PDF could not be created" in final[5]
    assert final[7] is result
    assert final[8] is None
