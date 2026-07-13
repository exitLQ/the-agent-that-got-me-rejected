"""The Job Scout agent graph.

ONE compiled LangGraph serves the whole project. In Phase 1 the topology is:

    START -> extract_profile -> fetch_jobs -> rank_jobs -> [should_reformulate]
                                   ^                              |
                                   └──── reformulate_query ◄──────┘
                                                                  |
                                                                 END

Why one graph, not two (a design decision that pays off in Phase 2): the tailor
step will be a second entry into THIS graph on the same checkpointer thread, so
it can read the already-computed ``profile`` and ``ranked_jobs`` from the
checkpoint without re-running extraction or search. Two separate graphs could
not share that thread state. Phase 2 adds only a conditional entry router and a
``tailor`` node; the ranking pipeline below does not change.

The conditional edge after ranking is what makes this an agent rather than a
straight-line workflow: if too few strong matches came back, it loops through
``reformulate_query`` to broaden the search — capped at 2 reformulations.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from job_scout.nodes.extract_profile import extract_profile
from job_scout.nodes.fetch_jobs import fetch_jobs
from job_scout.nodes.rank_jobs import rank_jobs
from job_scout.nodes.reformulate_query import reformulate_query
from job_scout.schemas import AgentState

GOOD_FIT_THRESHOLD = 60
MIN_GOOD_JOBS = 5
MAX_REFORMULATIONS = 2


def should_reformulate(state: AgentState) -> str:
    """Route after ranking: loop to broaden the search, or finish.

    Loops only if there are fewer than ``MIN_GOOD_JOBS`` jobs scoring at least
    ``GOOD_FIT_THRESHOLD`` AND we are under the reformulation cap. Hitting the
    cap with thin results is interesting trace material — it is not an error.
    """
    ranked = state.get("ranked_jobs", [])
    good = sum(1 for r in ranked if r.fit_score >= GOOD_FIT_THRESHOLD)
    if good < MIN_GOOD_JOBS and state.get("reformulation_count", 0) < MAX_REFORMULATIONS:
        return "reformulate_query"
    return END


def build_graph(checkpointer: MemorySaver | None = None):
    """Build and compile the agent graph.

    Phase 1 connects START directly to extract_profile. Phase 2 replaces that
    single edge with a conditional entry router (selected_job_id → tailor).
    """
    builder = StateGraph(AgentState)
    builder.add_node("extract_profile", extract_profile)
    builder.add_node("fetch_jobs", fetch_jobs)
    builder.add_node("rank_jobs", rank_jobs)
    builder.add_node("reformulate_query", reformulate_query)

    builder.add_edge(START, "extract_profile")
    builder.add_edge("extract_profile", "fetch_jobs")
    builder.add_edge("fetch_jobs", "rank_jobs")
    builder.add_conditional_edges("rank_jobs", should_reformulate, ["reformulate_query", END])
    builder.add_edge("reformulate_query", "fetch_jobs")

    return builder.compile(checkpointer=checkpointer or MemorySaver())
