"""Visible disclosure for local and cloud model execution."""

from __future__ import annotations

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
    )
    monkeypatch.setattr(app, "get_settings", lambda: settings)

    html = app._footer_html(RunResult())

    assert "cloud LLM: CV content sent to anthropic" in html
    assert "privacy: raw resume discarded" in html
    assert "cost: check provider dashboard" in html
