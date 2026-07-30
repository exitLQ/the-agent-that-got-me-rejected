"""Graph routing, loop guard, and the LLM call budget."""

from __future__ import annotations

import pytest
from langgraph.runtime import Runtime

import job_scout.graph.graph as graph_mod
from job_scout.corpus import CorpusItem
from job_scout.graph.graph import END, build_graph, route_entry, should_reformulate
from job_scout.graph.schemas import JobPosting, RankedJob
from job_scout.graph.state import AgentContext
from job_scout.llm import LLMBudgetExceededError, ensure_budget


def _ranked(score: int) -> RankedJob:
    job = JobPosting(job_id="x", title="t", company="c", location="l", source="cache")
    return RankedJob(job=job, fit_score=score, fit_explanation="e")


def test_entry_routes_explicit_selection_to_tailoring():
    assert route_entry({"selected_job_id": "job-1"}) == "tailor"


def test_entry_routes_missing_selection_to_search():
    assert route_entry({"selected_job_id": None}) == "fetch_jobs"


def test_compiled_graph_routes_selection_with_runtime_only_context(
    monkeypatch,
    sample_profile,
):
    seen = {}
    corpus = (
        CorpusItem(
            item_id="cv-skill-001",
            text="Python",
            kind="skill",
        ),
    )

    def fake_tailor(state, runtime: Runtime[AgentContext]):
        seen["selected_job_id"] = state["selected_job_id"]
        seen["context"] = runtime.context
        return {"errors": ["tailor route reached"]}

    monkeypatch.setattr(graph_mod, "tailor_application", fake_tailor)
    graph = build_graph()
    config = {"configurable": {"thread_id": "tailor-route-test"}}
    final = graph.invoke(
        {
            "profile": sample_profile,
            "ranked_jobs": [_ranked(80)],
            "selected_job_id": "x",
        },
        config=config,
        context=AgentContext(candidate_corpus=corpus, tailor_model="ollama:test"),
    )

    assert seen["selected_job_id"] == "x"
    assert seen["context"].candidate_corpus == corpus
    assert final["errors"] == ["tailor route reached"]
    assert "candidate_corpus" not in graph.get_state(config).values


def test_route_loops_when_few_good_and_under_cap():
    state = {"ranked_jobs": [_ranked(70)], "reformulation_count": 0}
    assert should_reformulate(state) == "reformulate_query"


def test_route_ends_when_enough_good_jobs():
    state = {"ranked_jobs": [_ranked(70)] * 5, "reformulation_count": 0}
    assert should_reformulate(state) == END


def test_route_ends_when_reformulation_cap_hit():
    state = {"ranked_jobs": [_ranked(70)], "reformulation_count": 2}
    assert should_reformulate(state) == END


def test_route_ignores_low_scores_toward_quota():
    # 5 jobs but none >= 60 -> still loops (under cap)
    state = {"ranked_jobs": [_ranked(50)] * 5, "reformulation_count": 1}
    assert should_reformulate(state) == "reformulate_query"


def test_budget_allows_under_limit():
    ensure_budget(current_calls=10, planned=5, max_calls=25)  # no raise


def test_budget_raises_over_limit():
    with pytest.raises(LLMBudgetExceededError):
        ensure_budget(current_calls=24, planned=2, max_calls=25)
