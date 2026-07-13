# Opik setup

Job Scout traces every run in [Opik](https://www.comet.com/docs/opik/) (Comet's
LLM observability tool). This guide covers Phase 1. Later sections are stubs that
Phases 2 and 3 fill in.

## 1. Account & keys

1. Sign up at [comet.com](https://www.comet.com/) (free tier is enough).
2. Grab your **API key** from account settings and your **workspace** name.
3. Put them in `.env`:
   ```
   OPIK_API_KEY=...
   OPIK_WORKSPACE=your-workspace
   OPIK_PROJECT_NAME=job-scout
   OPIK_ENABLED=true
   ```

Pinned SDK version: **opik 2.1.x** (see `pyproject.toml`). Opik ships weekly; if
an integration call changes, check <https://www.comet.com/docs/opik/latest>.

## 2. What gets traced

The SDK is configured once at startup (`src/job_scout/tracing.py::configure_opik`).
Each run wraps the compiled graph with `track_langgraph`, which:

- Produces a **span tree per graph node** (extract_profile → fetch_jobs →
  rank_jobs → …).
- Enables **Show Agent Graph** in the trace sidebar (graph auto-extracted).
- Auto-computes **per-run cost** for OpenAI models (e.g. gpt-4o-mini).

Per run we also attach:

- **The uploaded CV PDF** as a trace attachment (`attach_cv`) — Phase 2's
  PDF-aware judge reasons over it.
- **Metadata**: `git_sha`, `model`, `jobs_source`, reformulation count, job
  counts.
- **Tags**: `phase-1`, and `ui` (app) or `batch` (baseline runner).
- **thread_id**: the Gradio session id, so Phase 2's second invocation lands on
  the same thread.

## 3. Prompt library

The prompt constants in `src/job_scout/prompts/` are registered in the Opik
prompt library at startup (`register_prompts`). The local constants remain the
source of truth; Opik mirrors them and versions on content change. Phase 3's
optimizer depends on this version history.

## 4. Verifying it works

Run the app (`make app`), upload a fixture CV, and open the project in Opik. You
should see: the span tree, a working **Show Agent Graph**, a cost > $0 (for API
models), and the CV attached to the trace.

## 5. Online evaluation rules — _Phase 2_

_To be documented in Phase 2: configuring Hallucination + FitExplanationQuality
online rules, including the PDF-attachment-aware judge._

## 6. Annotation queues — _Phase 2_

_To be documented in Phase 2: annotation queue over low-fit and
fabrication-flagged traces._
