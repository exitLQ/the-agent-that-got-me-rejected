"""Runner contract: the search always passes selected_job_id explicitly.

This is the state-reset guarantee from the spec — a run must never route into
stale Phase-2 tailoring state on a reused checkpointer thread.
"""

from __future__ import annotations

from types import SimpleNamespace

import job_scout.runner as runner_mod
from job_scout.runner import run_once, stream_search


class _FakeGraph:
    def __init__(self):
        self.captured_inputs = None

    def stream(self, inputs, config, stream_mode):
        self.captured_inputs = inputs
        return iter([])  # no node updates

    def get_state(self, config):
        return SimpleNamespace(
            values={
                "profile": None,
                "ranked_jobs": [],
                "jobs_sources": ["cache"],
                "query_history": ["data scientist", "data analyst"],
                "ranking_batch_count": 3,
                "ranking_workers": 2,
                "ranking_latency_s": 0.75,
                "ranking_failed_batches": 0,
            }
        )


def _patch(monkeypatch, fake):
    monkeypatch.setattr(runner_mod, "build_graph", lambda: fake)
    monkeypatch.setattr(runner_mod, "trace_graph", lambda g, t: g)
    monkeypatch.setattr(runner_mod, "get_tracer", lambda *a, **k: None)


def test_search_passes_profile_and_nulls_selected_job_id(monkeypatch, sample_profile):
    fake = _FakeGraph()
    _patch(monkeypatch, fake)
    monkeypatch.setattr(runner_mod, "extract_profile", lambda *a, **k: sample_profile)

    run_once("cv text here", thread_id="t1", tags=["batch"])

    assert fake.captured_inputs["profile"] is sample_profile
    assert fake.captured_inputs["selected_job_id"] is None
    assert "cv_text" not in fake.captured_inputs


def test_stream_search_yields_result(monkeypatch, sample_profile):
    fake = _FakeGraph()
    _patch(monkeypatch, fake)

    events = list(
        stream_search(
            sample_profile,
            thread_id="t1",
            tags=["ui"],
            model_name="anthropic:claude-sonnet-4-6",
        )
    )
    assert events[-1][0] == "result"
    result = events[-1][1]
    assert fake.captured_inputs["model"] == "anthropic:claude-sonnet-4-6"
    assert result.model == "anthropic:claude-sonnet-4-6"
    assert result.jobs_sources == ["cache"]
    assert result.query_history == ["data scientist", "data analyst"]
    assert result.ranking_batch_count == 3
    assert result.ranking_workers == 2
    assert result.ranking_latency_s == 0.75
    assert result.failed is False
