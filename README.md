<div align="center">

# Job Scout

**A LangGraph job-matching agent with full Opik observability.**

*Prepares applications, never submits them.*

</div>

Upload your CV (PDF) and Job Scout extracts a structured profile, fetches real
job openings, and ranks each with a **fit score (0–100)** and an explanation of
why it matches and where the gaps are. Every LLM and tool call is traced in
[Opik](https://www.comet.com/docs/opik/) from the very first run.

**The human applies. The agent never submits applications** — a deliberate
product and ethics decision.

---

## What you'll build

This repo is built in three phases (**Build → Evaluate → Self-Improve**), each
backing one post in the series and tagged in git.

| Phase | Tag | What it adds | Post |
|---|---|---|---|
| 1 | `phase-1` | Working agent + Gradio UI + Opik tracing from run one + baseline batch | _(link TBD)_ |
| 2 | `phase-2` | Tailoring node + full evaluation stack (datasets, metrics, online rules) | _(link TBD)_ |
| 3 | `phase-3` | Self-improvement loop (Test Suites, Ollie debugging, prompt optimization) | _(link TBD)_ |

> **You are on Phase 1.** The agent's LLM output is *deliberately unoptimized*
> here (first-draft prompts, no quality retries) — measuring and improving it is
> exactly what Phases 2 and 3 are about.

### Architecture (Phase 1)

```
START → extract_profile → fetch_jobs → rank_jobs → [enough good matches?]
                             ↑                              │ no
                             └──── reformulate_query ◄──────┘
                                                            │ yes
                                                           END
```

`fetch_jobs` is an LLM tool-calling node: the model reads the profile and
*chooses* the `search_jobs` arguments. The search fans out over **Adzuna**
(primary, international), **Remotive** (keyless remote jobs), and a **committed
cache** (offline fallback). See `docs/extending_sources.md`.

---

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Optional keys (the app runs without any — see below): OpenAI, Opik, Adzuna.

## Quickstart

```bash
git clone <this-repo> && cd jobhunter
uv sync --all-groups            # install
cp .env.example .env            # add keys (all optional; see below)
make test                       # 32 tests, no keys needed
make app                        # launch the Gradio app
```

Then upload a CV from `data/fixture_cvs/` and click **Find jobs**.

**Running with zero keys:** the app falls back to Remotive (keyless) + the
committed `data/cached_jobs.json`, and skips tracing. For the full lesson (real
cost in Opik, live international jobs), add `OPENAI_API_KEY`, `OPIK_API_KEY` /
`OPIK_WORKSPACE`, and `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`.

**Default model** is `gpt-4o-mini` (so Opik reports real cost). Swap it with
`SCOUT_MODEL` — e.g. `groq:llama-3.3-70b-versatile` (free, `uv sync --extra
groq`) or `ollama:llama3.2` (local). Free models show $0.00 cost in Opik.

## Commands

```bash
make setup       # uv sync + pre-commit hooks
make app         # launch Gradio
make batch       # baseline batch (prints projected cost; add --yes to run)
make snapshot    # rebuild data/cached_jobs.json from live sources
make fixtures    # regenerate the synthetic fixture CVs
make test        # pytest
make lint        # ruff check
make format      # ruff format + fix
```

## Repository layout

```
src/job_scout/
  config.py        schemas.py        graph.py        tracing.py        app.py
  runner.py        llm.py
  tools/           jobs_api.py (Adzuna/Remotive/cache), cv_reader.py
  nodes/           extract_profile, fetch_jobs, rank_jobs, reformulate_query
  prompts/         first-draft prompt constants (Phase 3 optimizes rank_jobs)
scripts/           run_batch.py, snapshot_jobs.py, generate_fixture_cvs.py
data/              cached_jobs.json, fixture_cvs/ (4 synthetic CVs)
docs/              opik_setup.md, extending_sources.md
reports/           baseline.json, phase1_findings.md
notebooks/         phase1_walkthrough.ipynb
tests/             32 unit tests (LLM mocked, Opik off)
```

## Troubleshooting

- **No jobs / all `source: cache`** — you have no Adzuna keys, or the network is
  blocked. Expected; the cache is the offline fallback. Add Adzuna keys and
  re-run `make snapshot` for international coverage.
- **Cost shows $0.00** — you're on a free model (Groq/Ollama). Opik only prices
  OpenAI/Anthropic/Google models.
- **No traces in Opik** — check `OPIK_ENABLED=true` and that `OPIK_API_KEY` /
  `OPIK_WORKSPACE` are set. See `docs/opik_setup.md`.
- **`init_chat_model` credential error** — set the key for your `SCOUT_MODEL`
  provider (e.g. `OPENAI_API_KEY`).

## Reproducibility & determinism

Extraction, ranking and reformulation run at temperature 0. Some residual
nondeterminism remains (model updates, tie-breaking). The committed cache and
pinned dependencies (`uv.lock`) keep the reader's experience stable.

## Conventions

Production-grade engineering, kept deliberately light for a teaching repo.
**Used here:** `src/` layout with clear layer separation; Pydantic schemas as
first-class citizens; `pydantic-settings` + `@lru_cache get_settings` +
`SecretStr`; graph = `nodes/` (functions returning state dicts) + one `graph.py`;
prompts as Python constants with Opik as a mirror (local constants are the source
of truth); Opik disabled in tests; `uv` + `[dependency-groups]`, `ruff`
(line-length 130, `E501` off for prompts, `S`/`B` relaxed in tests),
`pre-commit`, `pytest` with `MagicMock`-based LLM mocking; self-documenting
`Makefile`; field-by-field `.env.example`.

**Deliberately kept out** (not needed at this scope): FastAPI /
routers / services / repositories layering, Postgres `AsyncPostgresSaver` (uses
`MemorySaver`), Alembic, Docker Compose, strict `mypy`, and async throughout
(sync is enough for a Gradio generator + sequential batch). Config is a single
flat `Settings` rather than nested `__` env groups, and models use
`init_chat_model` (provider-configurable) rather than a directly-constructed
client.

## License

MIT.
