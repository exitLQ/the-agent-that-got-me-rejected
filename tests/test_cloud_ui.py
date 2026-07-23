"""Visible disclosure for local and cloud model execution."""

from __future__ import annotations

import ast
import inspect
import textwrap
from types import SimpleNamespace

import job_scout.app as app
from job_scout.applications import ApplicationStore
from job_scout.graph.schemas import JobPosting, RankedJob
from job_scout.runner import RunResult


def test_cloud_warning_names_external_provider():
    html = app._cloud_warning_html("xai:grok-4.3")

    assert "Cloud model active" in html
    assert "sent to xai" in html
    assert app._cloud_warning_html("ollama:qwen3:8b") == ""


def test_footer_discloses_cloud_data_transfer(monkeypatch):
    settings = SimpleNamespace(
        offline_mode=False,
        privacy_mode=True,
        scout_model="anthropic:claude-sonnet-4-6",
        has_opik=False,
    )
    monkeypatch.setattr(app, "get_settings", lambda: settings)

    html = app._footer_html(RunResult(model="xai:grok-4.3"))

    assert "cloud LLM: CV content sent to xai" in html
    assert "privacy: raw resume discarded" in html
    assert "cost: check provider dashboard" in html
    assert "tracing: disabled" in html
    assert "view traces in Opik" not in html


def test_failed_run_mentions_trace_only_when_opik_is_active(monkeypatch):
    settings = SimpleNamespace(
        offline_mode=False,
        privacy_mode=False,
        scout_model="openai:gpt-5-mini",
        has_opik=True,
    )
    monkeypatch.setattr(app, "get_settings", lambda: settings)

    html = app._footer_html(RunResult(failed=True, error_message="provider failed"))

    assert "The trace has details." in html
    assert "view traces in Opik" in html


def test_main_passes_theme_and_css_to_gradio_launch(monkeypatch):
    captured = {}
    demo = SimpleNamespace(launch=lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(app, "build_app", lambda: demo)

    app.main()

    assert captured == {"theme": app.THEME, "css": app.CSS}


def test_provider_status_discloses_blocked_cloud_transfer(monkeypatch):
    status = SimpleNamespace(
        ready=False,
        external=True,
        message="Blocked by OFFLINE_MODE=true.",
    )
    monkeypatch.setattr(app, "model_configuration_status", lambda model: status)

    html = app._provider_status_html("anthropic", "claude-sonnet-4-6")

    assert "Not ready" in html
    assert "Blocked by OFFLINE_MODE=true." in html
    assert "anthropic:claude-sonnet-4-6" in html


def test_upload_rejects_blocked_provider_before_reading_resume(monkeypatch):
    monkeypatch.setattr(app, "get_settings", lambda: SimpleNamespace(privacy_mode=False))
    monkeypatch.setattr(
        app,
        "validate_model_configuration",
        lambda model: (_ for _ in ()).throw(app.ModelConfigurationError("blocked")),
    )
    monkeypatch.setattr(
        app,
        "extract_cv_text",
        lambda path: (_ for _ in ()).throw(AssertionError("resume was read")),
    )

    events = list(app.on_upload("resume.pdf", "thread", "openai", "gpt-5-mini"))

    assert len(events) == 1
    assert "Model is not ready: blocked" in events[0][3]
    assert events[0][4:] == (None, None)


def test_upload_keeps_selected_model_in_session_state(monkeypatch, sample_profile):
    captured = {}
    monkeypatch.setattr(app, "get_settings", lambda: SimpleNamespace(privacy_mode=False))
    monkeypatch.setattr(app, "validate_model_configuration", lambda model: "anthropic")
    monkeypatch.setattr(app, "extract_cv_text", lambda path: "synthetic resume")

    def fake_extract(cv_text, **kwargs):
        captured.update(kwargs)
        return sample_profile

    monkeypatch.setattr(app, "extract_profile", fake_extract)

    events = list(app.on_upload("resume.pdf", "thread", "anthropic", "claude-sonnet-4-6"))

    assert events[-1][4] is sample_profile
    assert events[-1][5] == "anthropic:claude-sonnet-4-6"
    assert captured["model_name"] == "anthropic:claude-sonnet-4-6"


def test_build_app_uses_the_gradio_6_blocks_api():
    tree = ast.parse(textwrap.dedent(inspect.getsource(app.build_app)))
    blocks_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Blocks"
    ]

    assert len(blocks_calls) == 1
    assert {keyword.arg for keyword in blocks_calls[0].keywords} == {"title"}


def test_save_ranked_application_refreshes_local_tracker(monkeypatch):
    store = ApplicationStore(":memory:")
    monkeypatch.setattr(app, "get_application_store", lambda: store)
    ranked = RankedJob(
        job=JobPosting(
            job_id="tracked-1",
            title="Data Engineer",
            company="Example",
            location="Remote",
            remote=True,
            description="Python role",
            url="https://example.com/job",
            source="cache",
        ),
        fit_score=88,
        fit_explanation="Strong match.",
    )

    feedback, dropdown, dashboard, status, tracked_notes, cleared_notes = app.save_ranked_application(
        [ranked],
        "tracked-1",
        "Applied",
        "Follow up Friday",
    )

    assert "Saved Data Engineer at Example" in feedback
    assert dropdown["value"] == "tracked-1"
    assert "Applied" in dashboard
    assert "Follow up Friday" in dashboard
    assert status["value"] == "Applied"
    assert tracked_notes == "Follow up Friday"
    assert cleared_notes == ""
    assert store.get("tracked-1").status == "Applied"
    store.close()


def test_dashboard_escapes_saved_job_content(monkeypatch):
    store = ApplicationStore(":memory:")
    monkeypatch.setattr(app, "get_application_store", lambda: store)
    ranked = RankedJob(
        job=JobPosting(
            job_id="unsafe",
            title="<script>alert(1)</script>",
            company="A & B",
            location="<Vienna>",
            description="",
            url='javascript:alert("unsafe")',
            source="cache",
        ),
        fit_score=50,
        fit_explanation="",
    )
    store.save(ranked, notes="<b>private</b>")

    html = app._application_dashboard_html()

    assert "<script>" not in html
    assert "javascript:" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;private&lt;/b&gt;" in html
    store.close()
