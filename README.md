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
- Strict offline mode using the committed job cache by default
- Optional live search through JSearch, Adzuna, and Remotive
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
OFFLINE_MODE=true
OPIK_ENABLED=false
```

No OpenAI key or job-source key is needed for this configuration. With
`OFFLINE_MODE=true`, job search uses only the committed cache.

### Updating an existing checkout

If `.env` already exists from an older version, `uv sync` does not overwrite it.
Update the model settings manually:

```dotenv
SCOUT_MODEL=ollama:qwen3:8b
SCOUT_TAILOR_MODEL=ollama:qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_HEALTH_TIMEOUT=3
OFFLINE_MODE=true
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

Ollama supplies local model inference. Strict offline mode, described below,
prevents job adapters and cloud tracing from making external requests.

## Strict offline mode

### What was implemented

Strict offline mode is enabled by default with:

```dotenv
OFFLINE_MODE=true
```

In this mode the application:

- searches only `data/cached_jobs.json`;
- does not initialize or call JSearch, Adzuna, or Remotive;
- disables Opik tracing even if an Opik API key is present;
- loads no external font stylesheet in the Gradio interface; and
- displays the cache job count and file date with a warning that cached results
  may be stale.

The local Ollama and Gradio connections still use HTTP on the loopback interface.
In this project, offline means that the application makes no external network
request during a run. The configured Ollama server should therefore remain on
`localhost` when strict isolation is required.

### Search behavior and stale data

The offline search ranks committed cache entries by the words in the generated
query, gives remote postings a small boost when remote work is requested,
removes duplicates, and returns at most the requested limit. It never silently
switches to a live provider. Precise cache location matching is intentionally
reserved for Point 3 of the improvement plan.

The interface footer reports:

```text
offline cache: <count> jobs, file date <YYYY-MM-DD>; results may be stale
```

The file date is the last-modified date of `data/cached_jobs.json`. It describes
the cache file, not the publication date of every job. A small or old cache can
produce few matches, and cached links may no longer be active.

### Enabling live job sources

Live providers are an explicit opt-in. Set:

```dotenv
OFFLINE_MODE=false
```

Then configure any desired provider:

```dotenv
JSEARCH_API_KEY=your-key
ADZUNA_APP_ID=your-id
ADZUNA_APP_KEY=your-key
```

With offline mode disabled, the cascade tries JSearch, Adzuna, Remotive, and
finally the cache. Remotive does not require a key but is still an external
service. To enable optional cloud tracing as well:

```dotenv
OFFLINE_MODE=false
OPIK_ENABLED=true
OPIK_API_KEY=your-key
```

`OPIK_ENABLED=true` has no effect while `OFFLINE_MODE=true`.

### Offline verification

Run the dedicated tests:

```bash
uv run pytest tests/test_offline_mode.py
```

They verify that live adapters are not called, an attempted job-search HTTP
request fails the test, Opik remains disabled despite configured credentials,
cache provenance is available, and the interface CSS contains no external font
import.

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

The model selects job-search arguments through a tool call. In the default
offline mode, search reads only cached data. With offline mode disabled, the
live adapters run before the cache fallback. Ranking runs in batches, and the
graph can broaden a weak search up to a fixed limit.

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
| `OFFLINE_MODE` | Restricts job search and tracing to local resources | No |
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

<!-- hypertribe:sponsors:start -->
## Sponsors

[![the-agent-that-got-me-rejected Sponsors](https://api.tribe.run/tokens/GitYLyzVihz9dXk5QJkML4bcRn2s1qZ996BHZK7TvrKd/sponsors.svg)](https://tribe.run/token/GitYLyzVihz9dXk5QJkML4bcRn2s1qZ996BHZK7TvrKd)

Become a sponsor on [Tribe.run](https://tribe.run/token/GitYLyzVihz9dXk5QJkML4bcRn2s1qZ996BHZK7TvrKd).
<!-- hypertribe:sponsors:end -->
