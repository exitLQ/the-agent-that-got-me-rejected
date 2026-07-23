"""Visible disclosure for local and cloud model execution."""

from __future__ import annotations

import ast
import inspect
import textwrap
from types import SimpleNamespace

import job_scout.app as app
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

    html = app._footer_html(RunResult())

    assert "cloud LLM: CV content sent to anthropic" in html
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
    monkeypatch.setattr(app, "get_settings", lambda: SimpleNamespace(scout_model="ollama:qwen3:8b"))
    monkeypatch.setattr(app, "validate_model_configuration", lambda model: "ollama")
    monkeypatch.setattr(app, "build_app", lambda: demo)

    app.main()

    assert captured == {"theme": app.THEME, "css": app.CSS}


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
