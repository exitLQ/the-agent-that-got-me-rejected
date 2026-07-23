"""Profile extraction (the preprocessing step before the graph)."""

from __future__ import annotations

import job_scout.profile as profile_mod
from job_scout.profile import extract_profile
from tests.conftest import structured_llm


def test_extract_profile(monkeypatch, sample_profile):
    captured = {}

    def fake_model(model_name, temperature):
        captured.update(model_name=model_name, temperature=temperature)
        return structured_llm(sample_profile)

    monkeypatch.setattr(profile_mod, "get_chat_model", fake_model)
    result = extract_profile("some cv text", model_name="anthropic:claude-sonnet-4-6")

    assert result is sample_profile
    assert captured == {"model_name": "anthropic:claude-sonnet-4-6", "temperature": 0.0}
