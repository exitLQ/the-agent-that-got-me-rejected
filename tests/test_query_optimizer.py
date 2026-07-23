"""Validation and deterministic fallback behavior for search queries."""

from __future__ import annotations

from job_scout.app import _query_audit_html, _results_html
from job_scout.graph.schemas import QueryReformulation
from job_scout.query_optimizer import fallback_query, query_key, sanitize_query
from job_scout.runner import RunResult


def test_sanitize_query_removes_labels_and_quotes():
    assert sanitize_query('Search query: "machine learning engineer python"') == (
        "machine learning engineer python"
    )


def test_sanitize_query_rejects_prose_urls_and_long_output():
    assert sanitize_query("https://example.com/jobs") is None
    assert sanitize_query("one two three four five six seven eight nine") is None
    assert sanitize_query("python AND sql") is None
    assert sanitize_query("Here is a better query") is None
    assert sanitize_query("") is None


def test_query_key_is_case_and_punctuation_insensitive():
    assert query_key("Data-Scientist") == query_key("data scientist")


def test_first_fallback_uses_adjacent_role_and_stays_novel(sample_profile):
    query = fallback_query(
        sample_profile,
        ["data scientist"],
        attempt=1,
    )

    assert query == "machine learning engineer python"
    assert query_key(query) != query_key("data scientist")


def test_second_fallback_uses_a_different_broadening_strategy(sample_profile):
    history = ["data scientist", "machine learning engineer python"]

    query = fallback_query(sample_profile, history, attempt=2)

    assert query == "data analyst"
    assert query_key(query) not in {query_key(item) for item in history}


def test_query_audit_renders_strategy_and_quality_metrics():
    result = RunResult(
        query_history=["data scientist", "data analyst"],
        reformulation_log=[
            QueryReformulation(
                attempt=1,
                previous_query="data scientist",
                query="data analyst",
                strategy="fallback",
                reason="rejected a query already present in history",
                jobs_seen=4,
                good_jobs=1,
                best_score=72,
            )
        ],
    )

    html = _query_audit_html(result)

    assert "Query audit (2 searches)" in html
    assert "attempt 1" in html
    assert "fallback" in html
    assert "4 jobs, 1 good, best 72" in html
    assert "Query audit" in _results_html(result)
