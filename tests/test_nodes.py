"""Node behaviour with mocked LLMs and search."""

from __future__ import annotations

import job_scout.graph.nodes.fetch_jobs as fetch_mod
import job_scout.graph.nodes.rank_jobs as rank_mod
import job_scout.graph.nodes.reformulate_query as reformulate_mod
from job_scout.graph.nodes.fetch_jobs import fetch_jobs
from job_scout.graph.nodes.rank_jobs import rank_jobs
from job_scout.graph.nodes.reformulate_query import reformulate_query
from job_scout.graph.schemas import JobScore, JobScores
from tests.conftest import make_job, plain_llm, structured_llm, tool_calling_llm


def test_fetch_jobs_uses_llm_tool_args(monkeypatch, sample_profile, sample_jobs):
    llm = tool_calling_llm([{"name": "search_jobs", "args": {"query": "ml engineer", "country": "de", "remote": True}}])
    monkeypatch.setattr(fetch_mod, "get_chat_model", lambda *a, **k: llm)
    captured = {}

    def fake_run_search(query, location, country, remote, limit, preferred_locations):
        captured.update(
            query=query,
            country=country,
            remote=remote,
            preferred_locations=preferred_locations,
        )
        return sample_jobs, ["adzuna"]

    monkeypatch.setattr(fetch_mod, "run_search", fake_run_search)
    out = fetch_jobs({"profile": sample_profile, "llm_calls": 1})
    assert captured == {
        "query": "ml engineer",
        "country": "de",
        "remote": True,
        "preferred_locations": ["Berlin, Germany"],
    }
    assert out["jobs"] == sample_jobs
    assert out["jobs_sources"] == ["adzuna"]
    assert out["search_query"] == "ml engineer"
    assert out["llm_calls"] == 2


def test_fetch_jobs_no_tool_call_fallback(monkeypatch, sample_profile, sample_jobs):
    llm = tool_calling_llm([])  # model issued no tool call
    monkeypatch.setattr(fetch_mod, "get_chat_model", lambda *a, **k: llm)
    monkeypatch.setattr(fetch_mod, "run_search", lambda **k: (sample_jobs, ["cache"]))
    out = fetch_jobs({"profile": sample_profile, "llm_calls": 0})
    assert any("no tool call" in e for e in out["errors"])
    assert out["jobs"] == sample_jobs


def test_rank_jobs_batches_by_five(monkeypatch, sample_profile):
    jobs = [make_job(f"j{i}", f"Role {i}", f"Co{i}") for i in range(7)]
    calls = []

    def fake_model(*a, **k):
        llm = structured_llm(None)

        def invoke(prompt):
            # return a score for whichever ids appear in this batch prompt
            ids = [j.job_id for j in jobs if f"job_id: {j.job_id}\n" in prompt]
            calls.append(len(ids))
            return JobScores(scores=[JobScore(job_id=i, fit_score=80, fit_explanation="ok") for i in ids])

        llm.with_structured_output.return_value.invoke.side_effect = invoke
        return llm

    monkeypatch.setattr(rank_mod, "get_chat_model", fake_model)
    out = rank_jobs({"profile": sample_profile, "jobs": jobs, "llm_calls": 2})
    assert len(calls) == 2  # 7 jobs -> batches of 5 + 2
    assert out["llm_calls"] == 4  # 2 + 2 batches
    assert len(out["ranked_jobs"]) == 7


def test_rank_jobs_empty_jobs(sample_profile):
    out = rank_jobs({"profile": sample_profile, "jobs": [], "llm_calls": 0})
    assert out["ranked_jobs"] == []


def test_rank_jobs_keeps_job_missing_from_llm_response(monkeypatch, sample_profile):
    jobs = [
        make_job("included", "Data Scientist", "Acme"),
        make_job("omitted", "ML Engineer", "Globex"),
    ]
    result = JobScores(
        scores=[
            JobScore(
                job_id="included",
                fit_score=80,
                fit_explanation="Model assessment.",
            )
        ]
    )
    monkeypatch.setattr(rank_mod, "get_chat_model", lambda *a, **k: structured_llm(result))

    out = rank_jobs({"profile": sample_profile, "jobs": jobs, "llm_calls": 0})
    by_id = {ranked.job.job_id: ranked for ranked in out["ranked_jobs"]}

    assert set(by_id) == {"included", "omitted"}
    assert by_id["included"].score_breakdown.llm == 80
    assert by_id["omitted"].fit_score == by_id["omitted"].score_breakdown.deterministic
    assert "deterministic signals only" in by_id["omitted"].fit_explanation


def test_rank_jobs_uses_job_id_as_final_tie_break(monkeypatch, sample_profile):
    jobs = [
        make_job("z-job", "Data Scientist", "Zeta"),
        make_job("a-job", "Data Scientist", "Alpha"),
    ]
    result = JobScores(
        scores=[
            JobScore(job_id=job.job_id, fit_score=80, fit_explanation="Equal.")
            for job in jobs
        ]
    )
    monkeypatch.setattr(rank_mod, "get_chat_model", lambda *a, **k: structured_llm(result))

    out = rank_jobs({"profile": sample_profile, "jobs": jobs, "llm_calls": 0})

    assert [ranked.job.job_id for ranked in out["ranked_jobs"]] == ["a-job", "z-job"]


def test_reformulate_increments_counter(monkeypatch, sample_profile):
    monkeypatch.setattr(reformulate_mod, "get_chat_model", lambda *a, **k: plain_llm("data analyst"))
    state = {"profile": sample_profile, "search_query": "data scientist", "reformulation_count": 0, "llm_calls": 3}
    out = reformulate_query(state)
    assert out["search_query"] == "data analyst"
    assert out["reformulation_count"] == 1
    assert out["llm_calls"] == 4
