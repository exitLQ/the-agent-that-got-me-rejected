"""Node behaviour with mocked LLMs and search."""

from __future__ import annotations

import job_scout.graph.nodes.fetch_jobs as fetch_mod
import job_scout.graph.nodes.rank_jobs as rank_mod
import job_scout.graph.nodes.reformulate_query as reformulate_mod
from job_scout.graph.nodes.fetch_jobs import _dedupe_with_existing, fetch_jobs
from job_scout.graph.nodes.rank_jobs import rank_jobs
from job_scout.graph.nodes.reformulate_query import reformulate_query
from job_scout.graph.schemas import JobScore, JobScores, RankedJob
from tests.conftest import make_job, plain_llm, structured_llm, tool_calling_llm


def test_fetch_jobs_uses_llm_tool_args(monkeypatch, sample_profile, sample_jobs):
    llm = tool_calling_llm([{"name": "search_jobs", "args": {"query": "ml engineer", "country": "de", "remote": True}}])
    selected_models = []
    monkeypatch.setattr(
        fetch_mod,
        "get_chat_model",
        lambda model, **kwargs: selected_models.append(model) or llm,
    )
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
    out = fetch_jobs({"profile": sample_profile, "llm_calls": 1, "model": "xai:grok-4.3"})
    assert selected_models == ["xai:grok-4.3"]
    assert captured == {
        "query": "ml engineer",
        "country": "de",
        "remote": True,
        "preferred_locations": ["Berlin, Germany"],
    }
    assert out["jobs"] == sample_jobs
    assert out["jobs_sources"] == ["adzuna"]
    assert out["search_query"] == "ml engineer"
    assert out["query_history"] == ["ml engineer"]
    assert out["llm_calls"] == 2


def test_fetch_jobs_no_tool_call_fallback(monkeypatch, sample_profile, sample_jobs):
    llm = tool_calling_llm([])  # model issued no tool call
    monkeypatch.setattr(fetch_mod, "get_chat_model", lambda *a, **k: llm)
    monkeypatch.setattr(fetch_mod, "run_search", lambda **k: (sample_jobs, ["cache"]))
    out = fetch_jobs({"profile": sample_profile, "llm_calls": 0})
    assert any("no tool call" in e for e in out["errors"])
    assert out["jobs"] == sample_jobs


def test_fetch_retry_executes_reformulated_query_without_second_llm(monkeypatch, sample_profile, sample_jobs):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Retry must execute the validated query directly")

    monkeypatch.setattr(fetch_mod, "get_chat_model", fail_if_called)
    captured = {}

    def fake_run_search(**kwargs):
        captured.update(kwargs)
        return sample_jobs, ["cache"]

    monkeypatch.setattr(fetch_mod, "run_search", fake_run_search)
    out = fetch_jobs(
        {
            "profile": sample_profile,
            "search_query": "data analyst python",
            "query_history": ["data scientist"],
            "reformulation_count": 1,
            "llm_calls": 3,
        }
    )

    assert captured["query"] == "data analyst python"
    assert out["query_history"] == ["data scientist", "data analyst python"]
    assert out["llm_calls"] == 3


def test_retry_merge_prioritizes_new_unique_results():
    existing = [make_job(f"old-{index}", f"Old Role {index}", f"Old Co {index}") for index in range(25)]
    new = [
        make_job("new", "New Role", "New Co"),
        make_job("duplicate", "Old Role 0", "Old Co 0"),
    ]

    merged = _dedupe_with_existing(existing, new, prefer_new=True)[:25]

    assert merged[0].job_id == "new"
    assert len(merged) == 25
    assert sum(job.title == "Old Role 0" for job in merged) == 1


def test_rank_jobs_batches_by_five(monkeypatch, sample_profile):
    jobs = [make_job(f"j{i}", f"Role {i}", f"Co{i}") for i in range(7)]
    calls = []
    selected_models = []

    def fake_model(model_name, **kwargs):
        selected_models.append(model_name)
        llm = structured_llm(None)

        def invoke(prompt):
            # return a score for whichever ids appear in this batch prompt
            ids = [j.job_id for j in jobs if f"job_id: {j.job_id}\n" in prompt]
            calls.append(len(ids))
            return JobScores(scores=[JobScore(job_id=i, fit_score=80, fit_explanation="ok") for i in ids])

        llm.with_structured_output.return_value.invoke.side_effect = invoke
        return llm

    monkeypatch.setattr(rank_mod, "get_chat_model", fake_model)
    out = rank_jobs(
        {
            "profile": sample_profile,
            "jobs": jobs,
            "llm_calls": 2,
            "model": "anthropic:claude-sonnet-4-6",
        }
    )
    assert selected_models == ["anthropic:claude-sonnet-4-6"]
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


def test_rank_jobs_replaces_ungrounded_model_skill_claims(monkeypatch, sample_profile):
    job = make_job("grounded", "Data Scientist", "Acme")
    job.description = "Python skills and AWS experience are required."
    result = JobScores(
        scores=[
            JobScore(
                job_id=job.job_id,
                fit_score=80,
                fit_explanation="Assessment.",
                matched_skills=["Quantum Computing"],
                gaps=["Public speaking"],
            )
        ]
    )
    monkeypatch.setattr(rank_mod, "get_chat_model", lambda *a, **k: structured_llm(result))

    out = rank_jobs({"profile": sample_profile, "jobs": [job], "llm_calls": 0})
    ranked = out["ranked_jobs"][0]

    assert ranked.matched_skills == ["python"]
    assert ranked.gaps == ["AWS"]
    assert ranked.matched_skill_evidence[0].job_evidence.startswith("description:")
    assert ranked.gap_evidence[0].profile_evidence == "not present in profile.skills"


def test_reformulate_increments_counter(monkeypatch, sample_profile):
    llm = plain_llm("data analyst")
    selected_models = []
    monkeypatch.setattr(
        reformulate_mod,
        "get_chat_model",
        lambda model, **kwargs: selected_models.append(model) or llm,
    )
    state = {
        "profile": sample_profile,
        "search_query": "data scientist",
        "reformulation_count": 0,
        "llm_calls": 3,
        "model": "openai:gpt-5-mini",
    }
    out = reformulate_query(state)
    assert selected_models == ["openai:gpt-5-mini"]
    assert out["search_query"] == "data analyst"
    assert out["reformulation_count"] == 1
    assert out["llm_calls"] == 4
    assert out["reformulation_log"][0].strategy == "model"
    prompt = llm.invoke.call_args.args[0]
    assert "jobs seen: 0" in prompt
    assert "Queries already tried:\ndata scientist" in prompt


def test_reformulate_rejects_repeated_query_and_records_diagnostics(
    monkeypatch,
    sample_profile,
):
    monkeypatch.setattr(
        reformulate_mod,
        "get_chat_model",
        lambda *a, **k: plain_llm("data scientist"),
    )
    weak = make_job("weak", "Data Scientist", "Acme")
    state = {
        "profile": sample_profile,
        "search_query": "data scientist",
        "query_history": ["data scientist"],
        "ranked_jobs": [
            RankedJob(
                job=weak,
                fit_score=55,
                fit_explanation="Weak.",
                gaps=["AWS"],
            )
        ],
        "reformulation_count": 0,
        "llm_calls": 3,
    }

    out = reformulate_query(state)
    record = out["reformulation_log"][0]

    assert out["search_query"] == "machine learning engineer python"
    assert record.strategy == "fallback"
    assert "already present" in record.reason
    assert record.jobs_seen == 1
    assert record.good_jobs == 0
    assert record.best_score == 55
