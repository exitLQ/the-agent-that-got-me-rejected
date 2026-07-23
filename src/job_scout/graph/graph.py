"""Job-finding graph for the-agent-that-got-me-rejected.

The graph takes an already-extracted ``Profile`` as input (extraction is a
separate step — see ``job_scout.profile``) and focuses on finding jobs:

    START -> fetch_jobs -> rank_jobs -> [should_reformulate]
                ^                              |
                └──── reformulate_query ◄──────┘
                                               |
                                              END

The conditional edge after ranking is what makes this an agent rather than a
straight-line workflow: if too few strong matches came back, it loops through
``reformulate_query`` to broaden the search — capped at 2 reformulations.

One compiled graph serves the whole project. Phase 2 adds a conditional entry
router (``selected_job_id`` → a ``tailor`` node) that reads ``profile`` and
``ranked_jobs`` from the checkpointed thread; the search pipeline below does not
change.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from job_scout.graph.nodes.fetch_jobs import fetch_jobs
from job_scout.graph.nodes.rank_jobs import rank_jobs
from job_scout.graph.nodes.reformulate_query import reformulate_query
from job_scout.graph.state import AgentState

GOOD_FIT_THRESHOLD = 60
MIN_GOOD_JOBS = 5
MAX_REFORMULATIONS = 2


def should_reformulate(state: AgentState) -> str:
    """Route after ranking: loop to broaden the search, or finish.

    Loops only if there are fewer than ``MIN_GOOD_JOBS`` jobs scoring at least
    ``GOOD_FIT_THRESHOLD`` and we are under the reformulation cap. Reaching the
    cap with thin results is expected, not an error.
    """
    ranked = state.get("ranked_jobs", [])
    good = sum(1 for r in ranked if r.fit_score >= GOOD_FIT_THRESHOLD)
    if good < MIN_GOOD_JOBS and state.get("reformulation_count", 0) < MAX_REFORMULATIONS:
        return "reformulate_query"
    return END


def build_graph(checkpointer: MemorySaver | None = None):
    """Build and compile the job-finding graph (starts from the profile input)."""
    builder = StateGraph(AgentState)
    builder.add_node("fetch_jobs", fetch_jobs)
    builder.add_node("rank_jobs", rank_jobs)
    builder.add_node("reformulate_query", reformulate_query)

    builder.add_edge(START, "fetch_jobs")
    builder.add_edge("fetch_jobs", "rank_jobs")
    builder.add_conditional_edges("rank_jobs", should_reformulate, ["reformulate_query", END])
    builder.add_edge("reformulate_query", "fetch_jobs")

    return builder.compile(checkpointer=checkpointer or MemorySaver())
