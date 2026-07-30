"""Job-finding graph for the-agent-that-got-me-rejected.

The graph takes explicit current-run inputs. Without a selected job it focuses
on finding jobs:

    START -> fetch_jobs -> rank_jobs -> [should_reformulate]
                ^                              |
                └──── reformulate_query ◄──────┘
                                               |
                                              END

With an explicit selected job it enters the isolated application branch:

    START -> tailor -> END

The conditional edge after ranking is what makes this an agent rather than a
straight-line workflow: if too few strong matches came back, it loops through
``reformulate_query`` to broaden the search — capped at 2 reformulations.

One compiled graph serves search and tailoring. A conditional entry router
selects ``tailor`` only when ``selected_job_id`` is explicitly present. The
runner supplies profile and ranked jobs on that invocation instead of relying
on sensitive or stale checkpoint state.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from job_scout.graph.nodes.fetch_jobs import fetch_jobs
from job_scout.graph.nodes.rank_jobs import rank_jobs
from job_scout.graph.nodes.reformulate_query import reformulate_query
from job_scout.graph.nodes.tailor import tailor_application
from job_scout.graph.state import AgentContext, AgentState

GOOD_FIT_THRESHOLD = 60
MIN_GOOD_JOBS = 5
MAX_REFORMULATIONS = 2


def route_entry(state: AgentState) -> str:
    """Route an explicit job selection to tailoring; otherwise start a search."""
    return "tailor" if state.get("selected_job_id") else "fetch_jobs"


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
    """Build and compile the shared search-and-tailoring graph."""
    builder = StateGraph(AgentState, context_schema=AgentContext)
    builder.add_node("fetch_jobs", fetch_jobs)
    builder.add_node("rank_jobs", rank_jobs)
    builder.add_node("reformulate_query", reformulate_query)
    builder.add_node("tailor", tailor_application)

    builder.add_conditional_edges(
        START,
        route_entry,
        ["fetch_jobs", "tailor"],
    )
    builder.add_edge("fetch_jobs", "rank_jobs")
    builder.add_conditional_edges("rank_jobs", should_reformulate, ["reformulate_query", END])
    builder.add_edge("reformulate_query", "fetch_jobs")
    builder.add_edge("tailor", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())
