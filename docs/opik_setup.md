# Opik setup

the-agent-that-got-me-rejected can optionally trace runs in
[Opik](https://www.comet.com/docs/opik/). This integration is not required for
local development.

## 1. Account & keys

1. Sign up at [comet.com](https://www.comet.com/) (free tier is enough).
2. Grab your **API key** from account settings and your **workspace** name.
3. Put them in `.env`:
   ```
   OPIK_API_KEY=...
   OPIK_WORKSPACE=your-workspace
   OPIK_PROJECT_NAME=the-agent-that-got-me-rejected
   OPIK_ENABLED=true
   ```

Pinned SDK version: **opik 2.1.x** (see `pyproject.toml`). Opik ships weekly; if
an integration call changes, check <https://www.comet.com/docs/opik/latest>.

## 2. What gets traced

The SDK is configured once at startup (`src/job_scout/tracing.py::configure_opik`).
Each run wraps the compiled graph with `track_langgraph`, which:

- Produces a **span tree per graph node** (fetch_jobs →
  rank_jobs → …).
- Enables **Show Agent Graph** in the trace sidebar (graph auto-extracted).
- Auto-computes **per-run cost** for OpenAI models (e.g. gpt-4o-mini).

Per run we also attach:

- **The uploaded CV PDF** as a trace attachment (`attach_cv`) for optional
  PDF-aware evaluation.
- **Metadata**: `git_sha`, `model`, `jobs_source`, reformulation count, job
  counts.
- **Tags**: run origin such as `ui` or `batch`.
- **thread_id**: the Gradio session id, allowing related invocations to be
  grouped.

## 3. Prompt library

The prompt constants in `src/job_scout/graph/prompts/` are registered in the Opik
prompt library at startup (`register_prompts`). The local constants remain the
source of truth; Opik mirrors them and creates a version when content changes.

## 4. Verifying it works

Run the app (`make app`), upload a fixture CV, and open the project in Opik. You
should see: the span tree, a working **Show Agent Graph**, a cost > $0 (for API
models), and the CV attached to the trace.

## 5. Optional evaluation

Evaluation rules and annotation workflows are not required for the local
application. Add them only when an external observability workflow is needed.
