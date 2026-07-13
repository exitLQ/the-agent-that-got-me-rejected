"""Opik instrumentation — the core lesson of Phase 1.

Every run (UI or batch) is traced: a span tree per graph node, the agent graph
visualization, per-run cost, and the uploaded CV attached to the trace so the
Phase 2 PDF-aware judge can reason over it.

Everything here is offline-safe: with ``OPIK_ENABLED=false`` or no API key, the
functions degrade to no-ops and return ``None``, so tests and keyless runs work.
The local prompt constants remain the source of truth; Opik mirrors them.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from job_scout.config import get_settings
from job_scout.prompts.extract_profile import EXTRACT_PROFILE_PROMPT, EXTRACT_PROFILE_PROMPT_NAME
from job_scout.prompts.rank_jobs import RANK_JOBS_PROMPT, RANK_JOBS_PROMPT_NAME
from job_scout.prompts.reformulate import REFORMULATE_PROMPT, REFORMULATE_PROMPT_NAME

_CONFIGURED = False


@lru_cache(maxsize=1)
def git_sha() -> str:
    """Short git sha for trace metadata (``unknown`` outside a checkout)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 - git resolved from PATH is intended
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent,
            timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def configure_opik() -> bool:
    """Configure the Opik SDK once. Returns True if tracing is active."""
    global _CONFIGURED
    settings = get_settings()
    if not settings.has_opik:
        return False
    if _CONFIGURED:
        return True
    import opik

    opik.configure(
        api_key=settings.opik_api_key.get_secret_value(),
        workspace=settings.opik_workspace or None,
        project_name=settings.opik_project_name,
        use_local=False,
        force=True,
    )
    _CONFIGURED = True
    return True


def get_tracer(thread_id: str, tags: list[str], metadata: dict[str, Any] | None = None):
    """Return an OpikTracer for this run, or ``None`` when tracing is disabled."""
    if not configure_opik():
        return None
    from opik.integrations.langchain import OpikTracer

    settings = get_settings()
    meta = {"git_sha": git_sha(), "model": settings.scout_model, **(metadata or {})}
    return OpikTracer(
        tags=tags,
        metadata=meta,
        thread_id=thread_id,
        project_name=settings.opik_project_name,
    )


def trace_graph(compiled_graph, tracer):
    """Wrap the compiled graph so runs are traced (auto graph viz). No-op if disabled."""
    if tracer is None:
        return compiled_graph
    from opik.integrations.langchain import track_langgraph

    return track_langgraph(compiled_graph, tracer)


def attach_cv(tracer, pdf_path: str | Path) -> None:
    """Attach the uploaded CV PDF to the run's trace (best effort, post-run)."""
    if tracer is None:
        return
    try:
        import opik

        traces = tracer.created_traces()
        if not traces:
            return
        trace_id = getattr(traces[-1], "id", None)
        if not trace_id:
            return
        settings = get_settings()
        opik.Opik().queue_attachment_upload(
            entity_type="trace",
            entity_id=trace_id,
            project_name=settings.opik_project_name,
            file_path=str(pdf_path),
            file_name=Path(pdf_path).name,
            mime_type="application/pdf",
        )
    except Exception:  # noqa: BLE001, S110 - attachment is a nice-to-have, never fatal
        pass


def opik_url() -> str:
    """Best-effort dashboard link for the run footer."""
    settings = get_settings()
    ws = settings.opik_workspace
    if ws:
        return f"https://www.comet.com/opik/{ws}/projects"
    return "https://www.comet.com/opik/"


_PROMPTS = [
    (EXTRACT_PROFILE_PROMPT_NAME, EXTRACT_PROFILE_PROMPT),
    (RANK_JOBS_PROMPT_NAME, RANK_JOBS_PROMPT),
    (REFORMULATE_PROMPT_NAME, REFORMULATE_PROMPT),
]


def register_prompts() -> int:
    """Register/version the prompt constants in the Opik prompt library.

    Idempotent: creating a prompt whose content is unchanged is a no-op; changed
    content creates a new version. Returns the count registered (0 if disabled).
    """
    if not configure_opik():
        return 0
    import opik

    count = 0
    for name, text in _PROMPTS:
        try:
            opik.Prompt(name=name, prompt=text, validate_placeholders=False)
            count += 1
        except Exception:  # noqa: BLE001, S110 - never block a run on prompt sync
            pass
    return count
