"""Agent graph for the-agent-that-got-me-rejected."""

from typing import Any

__all__ = ["build_graph"]


def __getattr__(name: str) -> Any:
    """Load the graph builder lazily so schema imports cannot create a cycle."""
    if name == "build_graph":
        from job_scout.graph.graph import build_graph

        return build_graph
    raise AttributeError(name)
