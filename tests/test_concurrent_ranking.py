"""Bounded concurrent ranking with deterministic aggregation and isolation."""

from __future__ import annotations

import threading
from contextvars import ContextVar
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import job_scout.graph.nodes.rank_jobs as rank_mod
from job_scout.app import _footer_html
from job_scout.config import Settings
from job_scout.graph.nodes.rank_jobs import rank_jobs
from job_scout.graph.schemas import JobScore, JobScores
from job_scout.runner import RunResult
from tests.conftest import make_job


def _scores_for_prompt(prompt: str, jobs) -> JobScores:
    ids = [job.job_id for job in jobs if f"job_id: {job.job_id}\n" in prompt]
    return JobScores(
        scores=[
            JobScore(job_id=job_id, fit_score=80, fit_explanation="Concurrent.")
            for job_id in ids
        ]
    )


class _Model:
    def __init__(self, invoke):
        self.invoke = invoke

    def with_structured_output(self, schema):
        return self


def _settings(workers: int):
    return SimpleNamespace(
        scout_model="test:model",
        rank_max_workers=workers,
        max_llm_calls_per_run=25,
    )


def test_two_ranking_batches_overlap(monkeypatch, sample_profile):
    jobs = [make_job(f"j{index}", f"Role {index}", f"Co {index}") for index in range(10)]
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = 0
    peak = 0
    callback_context = ContextVar("callback_context", default="missing")
    seen_context = []

    def invoke(prompt):
        nonlocal active, peak
        seen_context.append(callback_context.get())
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait(timeout=3)
            return _scores_for_prompt(prompt, jobs)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(rank_mod, "get_settings", lambda: _settings(2))
    monkeypatch.setattr(rank_mod, "get_chat_model", lambda *a, **k: _Model(invoke))

    token = callback_context.set("propagated")
    try:
        out = rank_jobs({"profile": sample_profile, "jobs": jobs, "llm_calls": 1})
    finally:
        callback_context.reset(token)

    assert peak == 2
    assert seen_context == ["propagated", "propagated"]
    assert len(out["ranked_jobs"]) == 10
    assert out["ranking_batch_count"] == 2
    assert out["ranking_workers"] == 2
    assert out["ranking_failed_batches"] == 0
    assert out["llm_calls"] == 3


def test_worker_setting_one_runs_every_batch_sequentially(monkeypatch, sample_profile):
    jobs = [make_job(f"j{index}", f"Role {index}", f"Co {index}") for index in range(11)]
    calls = []

    def invoke(prompt):
        calls.append(prompt)
        return _scores_for_prompt(prompt, jobs)

    monkeypatch.setattr(rank_mod, "get_settings", lambda: _settings(1))
    monkeypatch.setattr(rank_mod, "get_chat_model", lambda *a, **k: _Model(invoke))

    out = rank_jobs({"profile": sample_profile, "jobs": jobs, "llm_calls": 0})

    assert len(calls) == 3
    assert len(out["ranked_jobs"]) == 11
    assert out["ranking_batch_count"] == 3
    assert out["ranking_workers"] == 1


def test_failed_batch_keeps_jobs_with_deterministic_scores(monkeypatch, sample_profile):
    jobs = [make_job(f"j{index}", f"Role {index}", f"Co {index}") for index in range(10)]

    def invoke(prompt):
        if "job_id: j0\n" in prompt:
            raise RuntimeError("simulated batch failure")
        return _scores_for_prompt(prompt, jobs)

    monkeypatch.setattr(rank_mod, "get_settings", lambda: _settings(2))
    monkeypatch.setattr(rank_mod, "get_chat_model", lambda *a, **k: _Model(invoke))

    out = rank_jobs({"profile": sample_profile, "jobs": jobs, "llm_calls": 0})
    by_id = {item.job.job_id: item for item in out["ranked_jobs"]}

    assert len(by_id) == 10
    assert out["ranking_failed_batches"] == 1
    assert any("batch 1 failed" in error for error in out["errors"])
    assert by_id["j0"].fit_score == by_id["j0"].score_breakdown.deterministic
    assert "deterministic signals only" in by_id["j0"].fit_explanation


def test_batch_cannot_score_job_from_another_batch(monkeypatch, sample_profile):
    jobs = [make_job(f"j{index}", f"Role {index}", f"Co {index}") for index in range(10)]

    def invoke(prompt):
        if "job_id: j0\n" in prompt:
            return JobScores(
                scores=[
                    JobScore(
                        job_id="j5",
                        fit_score=100,
                        fit_explanation="Cross-batch injection.",
                    )
                ]
            )
        return JobScores(scores=[])

    monkeypatch.setattr(rank_mod, "get_settings", lambda: _settings(2))
    monkeypatch.setattr(rank_mod, "get_chat_model", lambda *a, **k: _Model(invoke))

    out = rank_jobs({"profile": sample_profile, "jobs": jobs, "llm_calls": 0})
    by_id = {item.job.job_id: item for item in out["ranked_jobs"]}

    assert by_id["j5"].score_breakdown.llm == by_id["j5"].score_breakdown.deterministic
    assert "Cross-batch injection." not in by_id["j5"].fit_explanation


def test_worker_configuration_is_bounded():
    Settings(_env_file=None, RANK_MAX_WORKERS=1)
    Settings(_env_file=None, RANK_MAX_WORKERS=8)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, RANK_MAX_WORKERS=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, RANK_MAX_WORKERS=9)


def test_footer_exposes_ranking_metrics():
    result = RunResult(
        ranking_batch_count=5,
        ranking_workers=2,
        ranking_latency_s=1.234,
        ranking_failed_batches=1,
    )

    html = _footer_html(result)

    assert "ranking: 5 batches / 2 workers / 1.234s / 1 failed" in html
