# the-agent-that-got-me-rejected

the-agent-that-got-me-rejected is a local-first AI job-matching agent maintained by
[exitLQ](https://github.com/exitLQ).

Upload a CV as a PDF, extract a structured candidate profile, search multiple
job sources, and receive ranked openings with fit scores, matching skills, and
skill gaps. The application prepares research for a human user; it never submits
job applications.

## Maintainer

- Developer and maintainer: [exitLQ](https://github.com/exitLQ)
- Repository:
  [exitLQ/the-agent-that-got-me-rejected](https://github.com/exitLQ/the-agent-that-got-me-rejected)

## Features

- Typed CV profile extraction
- LangGraph agent with a bounded search-reformulation loop
- Job search through JSearch, Adzuna, Remotive, and an offline cache
- Batched job-fit ranking
- Gradio web interface
- Optional Opik tracing
- Offline fallback data for development and testing
- Guardrails for loop count and LLM-call budget

## Requirements

- Windows, macOS, or Linux
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/download) for local inference

OpenAI remains available as an optional provider, but it is no longer the
default.

## Installation

Clone the repository:

```bash
git clone https://github.com/exitLQ/the-agent-that-got-me-rejected.git
cd the-agent-that-got-me-rejected
```

Install the project with local Ollama support:

```bash
uv sync --extra ollama --all-groups
```

Create the local configuration:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Pull the default local model:

```bash
ollama pull qwen3:8b
```

The default `.env.example` configuration is:

```dotenv
SCOUT_MODEL=ollama:qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
OPIK_ENABLED=false
```

No OpenAI key is needed for this configuration. Job-source keys remain
optional. Without them, search falls back to Remotive and the committed cache.

### Updating an existing checkout

If `.env` already exists from an older version, `uv sync` does not overwrite it.
Update the model settings manually:

```dotenv
SCOUT_MODEL=ollama:qwen3:8b
SCOUT_TAILOR_MODEL=ollama:qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_HEALTH_TIMEOUT=3
```

Then install the extra and pull the model:

```bash
uv sync --extra ollama --all-groups
ollama pull qwen3:8b
```

## Local Ollama integration

### What was implemented

The application now treats Ollama as a first-class model provider:

- `langchain-ollama` is available through the `ollama` project extra.
- `SCOUT_MODEL` and `SCOUT_TAILOR_MODEL` default to `ollama:qwen3:8b`.
- `ChatOllama` is created directly instead of routing Ollama through an
  OpenAI-compatible endpoint.
- The same model interface continues to support structured profile extraction,
  tool selection, batched ranking, and query reformulation.
- The model client is cached after successful validation.

### Startup validation

Before the Gradio server starts, the application requests:

```text
GET http://localhost:11434/api/tags
```

This is Ollama's local model-list endpoint. Startup continues only when:

1. the Ollama service responds successfully; and
2. the exact model configured in `SCOUT_MODEL` is installed.

If Ollama is unavailable, startup exits with a message containing the configured
URL. If the model is missing, the message provides the exact pull command:

```bash
ollama pull qwen3:8b
```

The health check applies only to `ollama:` model strings. OpenAI and other cloud
providers do not trigger a request to the local Ollama endpoint.

### Ollama configuration

| Variable | Default | Description |
|---|---|---|
| `SCOUT_MODEL` | `ollama:qwen3:8b` | Main extraction, tool-calling, and ranking model |
| `SCOUT_TAILOR_MODEL` | `ollama:qwen3:8b` | Reserved tailoring model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_HEALTH_TIMEOUT` | `3` | Startup health-check timeout in seconds |

For Ollama running on another machine:

```dotenv
OLLAMA_BASE_URL=http://192.168.1.50:11434
```

Do not expose an unauthenticated Ollama server directly to the public internet.

### Switching back to OpenAI

Install the normal dependencies and configure:

```dotenv
SCOUT_MODEL=openai:gpt-4o-mini
SCOUT_TAILOR_MODEL=openai:gpt-4o-mini
OPENAI_API_KEY=your-key
```

No source-code change is required.

### Verification

List locally installed models:

```bash
ollama list
```

Check the API directly:

```bash
curl http://localhost:11434/api/tags
```

Run the automated Ollama integration tests:

```bash
uv run pytest tests/test_llm.py
```

These tests mock the local endpoint. They verify successful startup validation,
missing-model errors, unavailable-service errors, and that cloud models skip the
Ollama check. They do not download a model.

### Current scope

This point adds local model inference and startup validation. It does not yet
guarantee a network-isolated run because live job adapters may still call
external services. Strict network isolation is Point 2 in the
[local-first roadmap](docs/local_first_plan.md).

## Run the application

```bash
uv run python -m job_scout.app
```

Open <http://localhost:7860> and upload a PDF from `data/fixture_cvs/` or your
own CV.

For detailed operating-system instructions, configuration options, and common
errors, see [Local setup](docs/local_setup.md).

## Verification

Run the test suite:

```bash
uv run pytest
```

Run static checks:

```bash
uv run ruff check .
```

## Architecture

```text
CV PDF
  |
  v
Profile extraction
  |
  v
Fetch jobs -> Rank jobs -> Enough strong matches?
     ^                         |
     |                         | no, below loop limit
     +---- Reformulate query <-+
                               |
                               v
                         Ranked results
```

The model selects job-search arguments through a tool call. Search adapters then
query available sources and fall back to cached data. Ranking runs in batches,
and the graph can broaden a weak search up to a fixed limit.

See [Architecture](docs/architecture.md) for the detailed graph.

## Project structure

```text
src/job_scout/
  app.py              Gradio interface
  config.py           Environment configuration
  llm.py              Model initialization and call budget
  profile.py          CV-to-profile extraction
  runner.py           Shared application and batch runner
  tracing.py          Optional Opik integration
  graph/              LangGraph state, nodes, schemas, and prompts
  tools/              CV reader and job-source adapters
data/
  cached_jobs.json    Offline fallback postings
  fixture_cvs/        Synthetic test CVs
docs/                 Architecture, setup, and roadmap
scripts/              Batch and data-maintenance utilities
tests/                Offline automated tests
```

## Common commands

```bash
uv sync --extra ollama --all-groups
uv run python -m job_scout.app
uv run pytest
uv run ruff check .
uv run python scripts/run_batch.py --limit 3
```

## Configuration

Important environment variables:

| Variable | Purpose | Required |
|---|---|---|
| `SCOUT_MODEL` | Model used for extraction, search decisions, and ranking | Yes |
| `OLLAMA_BASE_URL` | Local Ollama service URL | For Ollama |
| `OLLAMA_HEALTH_TIMEOUT` | Ollama startup-check timeout | No |
| `OPENAI_API_KEY` | Authentication for an optional OpenAI model | For OpenAI |
| `OPIK_ENABLED` | Enables or disables external tracing | No |
| `JSEARCH_API_KEY` | Enables live JSearch results | No |
| `ADZUNA_APP_ID` | Enables Adzuna with `ADZUNA_APP_KEY` | No |
| `ADZUNA_APP_KEY` | Enables Adzuna with `ADZUNA_APP_ID` | No |
| `MAX_LLM_CALLS_PER_RUN` | Per-run LLM circuit breaker | No |

Never commit `.env` or API keys.

## Documentation

- [Local setup](docs/local_setup.md)
- [Local-first roadmap](docs/local_first_plan.md)
- [Architecture](docs/architecture.md)
- [Adding job sources](docs/extending_sources.md)
- [Optional Opik setup](docs/opik_setup.md)

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE).
The original copyright notice in that file is retained because the license
requires it to remain in redistributed copies.
