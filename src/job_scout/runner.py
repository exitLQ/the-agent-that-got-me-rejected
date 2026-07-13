"""Shared run orchestration used by both the Gradio app and the batch runner.

Centralizes: building the tracer, wrapping the graph, streaming node-level
status, measuring cost + latency locally (so the footer works even offline), and
attaching the CV to the trace. Keeping this in one place means the UI and batch
paths cannot drift apart.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from langchain_core.callbacks import UsageMetadataCallbackHandler

from job_scout.config import get_settings
from job_scout.graph import build_graph
from job_scout.schemas import Profile, RankedJob
from job_scout.tracing import attach_cv, get_tracer, opik_url, trace_graph

# USD per 1M tokens, for the local footer estimate. Opik is the source of truth
# in the dashboard; this table just powers the immediate footer number.
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
}

# Human-readable status per node, streamed to the UI.
_NODE_STATUS = {
    "extract_profile": "extracting profile…",
    "fetch_jobs": "searching jobs…",
    "rank_jobs": "ranking jobs…",
    "reformulate_query": "broadening the search…",
}


@dataclass
class RunResult:
    profile: Profile | None = None
    ranked_jobs: list[RankedJob] = field(default_factory=list)
    jobs_sources: list[str] = field(default_factory=list)
    reformulation_count: int = 0
    n_jobs_fetched: int = 0
    n_jobs_ranked: int = 0
    errors: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_s: float = 0.0
    opik_url: str = ""
    failed: bool = False
    error_message: str = ""


def _estimate_cost(usage: dict, model: str) -> float:
    key = model.split(":", 1)[-1]
    in_price, out_price = _PRICES.get(key, (0.0, 0.0))
    total = 0.0
    for stats in usage.values():
        total += stats.get("input_tokens", 0) / 1_000_000 * in_price
        total += stats.get("output_tokens", 0) / 1_000_000 * out_price
    return round(total, 6)


def stream_run(
    cv_text: str,
    *,
    cv_path: str | None = None,
    thread_id: str,
    tags: list[str],
    selected_job_id: str | None = None,
) -> Iterator[tuple[str, object]]:
    """Run the agent, yielding ``("status", msg)`` updates then ``("result", RunResult)``.

    The upload contract is honoured here: ``selected_job_id`` is passed
    explicitly (default ``None``) on every invocation, so a fresh CV never routes
    into stale Phase-2 tailoring state on a reused thread.
    """
    settings = get_settings()
    tracer = get_tracer(thread_id, tags)
    usage_cb = UsageMetadataCallbackHandler()
    callbacks = [usage_cb] + ([tracer] if tracer else [])

    graph = trace_graph(build_graph(), tracer)
    inputs = {"cv_text": cv_text, "selected_job_id": selected_job_id}
    config = {"configurable": {"thread_id": thread_id}, "callbacks": callbacks, "recursion_limit": 25}

    result = RunResult(opik_url=opik_url())
    start = time.monotonic()
    try:
        for chunk in graph.stream(inputs, config=config, stream_mode="updates"):
            for node_name, update in chunk.items():
                status = _NODE_STATUS.get(node_name, f"{node_name}…")
                if node_name == "fetch_jobs":
                    n = len(update.get("jobs", []))
                    attempt = update.get("reformulation_count", 0) + 1
                    status = f"searching jobs (attempt {attempt})… {n} found"
                elif node_name == "rank_jobs":
                    status = f"ranking {len(update.get('ranked_jobs', []))} jobs…"
                yield ("status", status)

        final = graph.get_state(config).values
        result.profile = final.get("profile")
        result.ranked_jobs = final.get("ranked_jobs", [])
        result.jobs_sources = final.get("jobs_sources", [])
        result.reformulation_count = final.get("reformulation_count", 0)
        result.n_jobs_fetched = len(final.get("jobs", []))
        result.n_jobs_ranked = len(result.ranked_jobs)
        result.errors = final.get("errors", [])
    except Exception as exc:  # noqa: BLE001 - surface as a failed run, keep the trace
        result.failed = True
        result.error_message = f"{type(exc).__name__}: {exc}"
    finally:
        result.latency_s = round(time.monotonic() - start, 2)
        result.cost_usd = _estimate_cost(usage_cb.usage_metadata, settings.scout_model)
        if cv_path:
            attach_cv(tracer, cv_path)
        if tracer:
            tracer.flush()

    yield ("result", result)


def run_once(
    cv_text: str,
    *,
    cv_path: str | None = None,
    thread_id: str,
    tags: list[str],
) -> RunResult:
    """Non-streaming convenience wrapper (used by the batch runner)."""
    result = RunResult()
    for kind, payload in stream_run(cv_text, cv_path=cv_path, thread_id=thread_id, tags=tags):
        if kind == "result":
            result = payload  # type: ignore[assignment]
    return result
