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
- An OpenAI API key for the current default model

Ollama-based fully local inference is part of the planned local-first migration.
See [Local-first roadmap](docs/local_first_plan.md).

## Installation

Clone the repository:

```bash
git clone https://github.com/exitLQ/the-agent-that-got-me-rejected.git
cd the-agent-that-got-me-rejected
```

Install the project:

```bash
uv sync --all-groups
```

Create the local configuration:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Add at least the following value to `.env`:

```dotenv
OPENAI_API_KEY=your-key
```

All other service keys are optional. Without job-source keys, the search falls
back to Remotive and the committed offline cache. Opik can be disabled:

```dotenv
OPIK_ENABLED=false
```

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
uv sync --all-groups
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
| `OPENAI_API_KEY` | Authentication for the default OpenAI model | For default model |
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
