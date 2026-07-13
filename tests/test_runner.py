"""Runner contract: every invocation passes selected_job_id explicitly.

This is the state-reset guarantee from the spec — a fresh CV must never route
into stale Phase-2 tailoring state on a reused checkpointer thread.
"""

from __future__ import annotations

from types import SimpleNamespace

import job_scout.runner as runner_mod
from job_scout.runner import run_once, stream_run


class _FakeGraph:
    def __init__(self):
        self.captured_inputs = None

    def stream(self, inputs, config, stream_mode):
        self.captured_inputs = inputs
        return iter([])  # no node updates

    def get_state(self, config):
        return SimpleNamespace(values={"profile": None, "ranked_jobs": [], "jobs_sources": ["cache"]})


def test_upload_passes_selected_job_id_none(monkeypatch):
    fake = _FakeGraph()
    monkeypatch.setattr(runner_mod, "build_graph", lambda: fake)
    monkeypatch.setattr(runner_mod, "trace_graph", lambda g, t: g)
    monkeypatch.setattr(runner_mod, "get_tracer", lambda *a, **k: None)

    run_once("cv text here", thread_id="t1", tags=["batch"])

    assert "selected_job_id" in fake.captured_inputs
    assert fake.captured_inputs["selected_job_id"] is None
    assert fake.captured_inputs["cv_text"] == "cv text here"


def test_stream_run_yields_result(monkeypatch):
    fake = _FakeGraph()
    monkeypatch.setattr(runner_mod, "build_graph", lambda: fake)
    monkeypatch.setattr(runner_mod, "trace_graph", lambda g, t: g)
    monkeypatch.setattr(runner_mod, "get_tracer", lambda *a, **k: None)

    events = list(stream_run("cv", thread_id="t1", tags=["ui"]))
    kinds = [k for k, _ in events]
    assert kinds[-1] == "result"
    result = events[-1][1]
    assert result.jobs_sources == ["cache"]
    assert result.failed is False
