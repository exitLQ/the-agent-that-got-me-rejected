# The Observable Job Agent — Part 1: Job Scout

## Summary

Job Scout is a real, observable AI agent you run on your own machine. You upload
your CV (PDF); it extracts a structured profile, searches real job openings, and
ranks each with a **fit score (0–100)** plus an honest explanation of what matches
and where your gaps are. Every LLM and tool call is traced in
[Opik](https://www.comet.com/docs/opik/) from the very first run.

It is Part 1 of a three-part series that builds one agent while building the
ability to see inside it: **Build → Evaluate → Self-Improve**.

> **The human applies. The agent never submits applications.** The bottleneck in
> a job hunt is the research and tailoring per application, not clicking submit.
> That is the part worth automating.

## Architecture

![Job Scout architecture](docs/images/architecture.png)

Your CV becomes a typed profile, then a LangGraph agent lets the model choose how
to search four job sources, scores the results in batches, and loops (bounded) to
broaden thin matches. Opik traces all of it. Full walkthrough in
[`docs/architecture.md`](docs/architecture.md).

## Key Features

**Core philosophy:** instrument before you optimize. The agent is traced from run
one, so cost, latency, and quality are measurable *before* any tuning. Phase 1's
prompts are deliberately first-draft; measuring them honestly is the whole point.

**Technology stack:**
- LangGraph (the agent graph + conditional reformulation loop)
- LangChain (`init_chat_model`, LLM-driven tool calling)
- Opik / Comet (observability: traces, cost, prompt versioning)
- Gradio (three-step wizard UI with streamed progress)
- Pydantic + pydantic-settings (typed schemas and config)
- httpx + pypdf (job-source HTTP, CV reading)
- uv, ruff, pytest (tooling)
- Job sources: JSearch, Adzuna, Remotive, and a committed offline cache

**Progressive learning path:**

| Part | Focus | Outcome |
|------|-------|---------|
| **1 (this repo)** | Build | Working agent + Gradio UI + Opik tracing from run one + a documented baseline |
| 2 | Extend, then evaluate | Tailoring node + datasets, LLM judges, and online evaluation rules |
| 3 | Self-improve | Test suites, prompt optimization, and trace-driven fixes with before/after numbers |

## Accessibility

- **Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/). API keys are optional.
- **Cost:** under **$0.50** to reproduce with API models, or **fully free** with local models (Ollama) or free tiers. Runs with **zero keys** via Remotive + the offline cache.
- **Quick start:**
  ```bash
  uv sync --all-groups      # install
  cp .env.example .env      # all keys optional
  make test                 # 35 tests, no network
  make app                  # launch the Gradio app, then upload a fixture CV
  ```
- **Access points:** Gradio UI (`http://localhost:7860`), Opik project dashboard (when tracing is enabled).

Deeper docs live in [`docs/`](docs/): architecture, Opik setup, and how to add a
job source.

## Created by

**Shirin** — [Jam with AI](https://jamwithai.substack.com).

*Jam with AI is a reader-supported publication on building production AI systems.*
