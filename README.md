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
- Batched job-fit ranking with a transparent hybrid score
- Evidence-backed matched skills and technology gaps
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
switches to a live provider. The precise location filter described below is
applied before results are returned.

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

## Precise location matching

### What was implemented

Location handling is deterministic and shared by cached and live results:

- Candidate and job locations are normalized without regard to case, accents,
  repeated whitespace, or punctuation.
- Country names, common abbreviations, translated names, cities, and regional
  labels are mapped to validated two-letter country codes.
- Country aliases are matched on word boundaries. For example, `Australia` is
  never interpreted as `US` merely because it contains those letters.
- Unknown locations remain unknown instead of silently defaulting to the United
  States.
- Every location extracted from the profile is considered. The first remains
  the primary location sent to a live provider, while post-filtering accepts an
  eligible result for any preferred location.
- The profile location is authoritative when it conflicts with a country code
  selected by the model.

### Match levels

Results are filtered and ordered with four explicit levels:

| Rank | Meaning | Example for `Berlin, Germany` |
|---|---|---|
| 4 | Exact city or equivalent locality | `Mitte, Berlin` |
| 3 | Eligible remote scope | `Worldwide` or `Europe only` |
| 2 | Same-country fallback | `Essen, Deutschland` |
| 1 | No location preference supplied | Provider order is preserved |
| 0 | Known mismatch | `London, UK` or `USA only` remote |

Exact matches appear before eligible remote roles, followed by same-country
fallbacks. The sort is stable within each level, so the source's relevance
ordering is preserved. Known mismatches are removed.

Translated city aliases are treated as the same place where configured. For
example, `Munich` matches `München`, `Vienna` matches `Wien`, and `Bangalore`
matches `Bengaluru`.

### Remote geography

The `remote` flag alone does not make a posting globally eligible. When remote
work is requested, the stated scope must include the candidate:

- `Worldwide`, `Global`, and `Anywhere` accept every country.
- `Europe`, `Americas`, `LATAM`, and `APAC` accept countries in their respective
  region.
- A country-specific remote role must match one of the profile's countries.

For example, a candidate in Germany who accepts remote work can receive a
`Europe only` posting but not a `USA only` posting.

### Provider behavior

JSearch and Adzuna use a country derived from the primary profile location.
They use a model-supplied country only when the location itself cannot be
resolved. Adzuna skips its request if neither value resolves to a supported
country, avoiding an accidental request to a guessed market.

After any provider responds, the same local match function filters its
normalized `JobPosting` objects. Offline cache results and online results
therefore follow identical location rules.

### Verification

Run the location and source tests:

```bash
uv run pytest tests/test_jobs_api.py tests/test_nodes.py
```

The tests cover accent normalization, word-boundary safety, translated cities,
exact and country-level ordering, multiple profile locations, remote regions,
unknown locations, provider behavior, deduplication, and result limits.

## Deterministic hybrid score

### Why the score changed

The model previously supplied the displayed fit score directly. Even with a
temperature of zero, that value could vary between models or overvalue a fluent
but weak assessment. The displayed score now uses a fixed public formula:

```text
final fit = round(0.60 × deterministic score + 0.40 × model score)
```

The model still contributes qualitative judgment and the written explanation,
but it cannot unilaterally determine ranking.

### Deterministic component

The deterministic score is itself a weighted calculation:

```text
deterministic score =
    0.40 × skills
  + 0.30 × role
  + 0.15 × seniority
  + 0.15 × location
```

| Component | Weight | Calculation |
|---|---:|---|
| Skills | 40% | Canonical profile-skill groups grounded in the job title, description, or tags |
| Role | 30% | Coverage of the best primary-role tokens by the job title |
| Seniority | 15% | Distance between profile seniority and explicit title seniority |
| Location | 15% | Exact city, eligible remote scope, same-country fallback, or mismatch |

Common technical punctuation is normalized before skill comparison. `C++`,
`C#`, `.NET`, `Node.js`, and `scikit-learn` therefore remain meaningful terms
instead of collapsing into ambiguous fragments.

When the profile has no skills or roles, that missing component receives a
neutral score of 50. A title without an explicit seniority receives 60. These
neutral values avoid treating absent metadata as either a perfect match or a
definite mismatch.

### Example

Suppose a job receives:

```text
skills       50
role        100
seniority    60
location    100
```

Its deterministic score is:

```text
round(50 × 0.40 + 100 × 0.30 + 60 × 0.15 + 100 × 0.15) = 74
```

If the model score is 80, the displayed fit is:

```text
round(74 × 0.60 + 80 × 0.40) = 76
```

Python uses round-to-even behavior for exact half values. All formula inputs
are integers from 0 to 100.

### Reliability behavior

Every fetched job remains in the result set even if the model accidentally
omits it from a batch response. For an omitted job, the deterministic score is
used as both formula inputs, so the final score equals the deterministic score.
The explanation explicitly states that no model assessment was returned.

Unknown job identifiers returned by the model are ignored. Final ordering uses
the following deterministic tie-break sequence:

1. final hybrid score, descending;
2. deterministic score, descending;
3. model score, descending; and
4. job identifier, ascending.

This prevents provider response order from deciding otherwise equal results.

### Score visibility

Each result card shows the final score in its gauge and exposes these values
below the explanation:

```text
rules 74  model 80  skills 50  role 100  seniority 60  location 100
```

The split makes it possible to see whether a high result is supported by
verifiable profile and posting data or mainly by the model assessment.

### Verification

Run the dedicated scoring and ranking tests:

```bash
uv run pytest tests/test_scoring.py tests/test_nodes.py tests/test_schemas.py
```

They verify the component weights, technical-term normalization, perfect
matches, inflated-model-score resistance, the 60/40 formula, score bounds,
batch behavior, and missing model assessments.

### Current boundary

The deterministic and model scores remain separate inputs. Evidence-backed
skill labels are described below and use the same canonical matches as the
skill component.

## Skill grounding

### Why grounding is required

The ranking model returns suggested `matched_skills` and `gaps`, but generated
lists can contain a plausible term that is absent from the CV, absent from the
job, optional rather than required, or merely a spelling variant of an existing
skill. Displaying those suggestions directly would make the result look more
certain than its source data supports.

The application now treats model skill lists as untrusted suggestions. A local,
deterministic resolver reconstructs the displayed lists from evidence.

### Grounded matches

A matched skill is displayed only when:

1. it exists in `profile.skills`; and
2. the same canonical skill group occurs in the job title, description, or
   tags.

The displayed spelling comes from the candidate profile. If the profile says
`ML` and the job says `machine learning`, the result displays `ML`, preserving
what the CV actually claimed.

Each match stores both provenance fields:

```text
profile.skills: <profile spelling>
title|tag|description: <job evidence>
```

Skills present only in the profile are not shown as matches for an unrelated
job. Skills claimed only by the model are discarded.

### Grounded gaps

A gap is displayed only for a technology in the controlled alias catalog when:

1. the technology is not represented in `profile.skills`;
2. it occurs in the job title, a job tag, or a description sentence with an
   explicit requirement cue; and
3. the evidence is not marked optional or negated.

Requirement cues include terms such as `required`, `must`, `experience`,
`knowledge`, `proficient`, and `skills`. Title and tag occurrences are treated
as direct requirement evidence.

Statements containing `optional`, `nice to have`, `bonus`, `not required`,
`not need`, or `no experience` are not promoted to gaps. This conservative rule
prefers omitting an uncertain gap over presenting an unsupported one.

### Canonical aliases

The resolver supports common equivalent forms, including:

| Canonical group | Example aliases |
|---|---|
| Machine Learning | `machine learning`, `ML` |
| AWS | `AWS`, `Amazon Web Services` |
| GCP | `GCP`, `Google Cloud Platform` |
| Kubernetes | `Kubernetes`, `k8s` |
| PostgreSQL | `PostgreSQL`, `Postgres` |
| JavaScript | `JavaScript`, `JS` |
| Node.js | `Node.js`, `nodejs` |
| scikit-learn | `scikit-learn`, `sklearn` |
| C++, C#, .NET | punctuation-preserving normalized forms |

Aliases use normalized word boundaries. For example, `JavaScript` does not
create a false `Java` match. Duplicate aliases in a profile collapse to one
canonical group and cannot inflate the skill score.

Profile skills outside the controlled catalog are still eligible for exact
normalized matching. Automatic gap discovery is intentionally limited to the
catalog because an unknown word cannot safely be classified as a technology
requirement.

### Evidence in the interface

Matched-skill and gap chips are derived from grounded evidence rather than
copied from the model response. Every result card includes an expandable
`Skill evidence` section containing:

```text
match: Python — profile.skills: Python — description: Python skills are required.
gap: AWS — not present in profile.skills — tag: AWS
```

The evidence text is escaped before rendering. Older saved `RankedJob` objects
without evidence remain valid because the new evidence fields default to empty
lists.

### Relationship to the hybrid score

The Point 4 skill component now counts the same canonical, evidence-backed
matches used by the interface. This prevents disagreement where an alias is
visible as a match but absent from the numeric skill score.

The model's free-text fit explanation remains a qualitative assessment. Skill
chips and their evidence section are the authoritative factual claims.

### Verification

Run the grounding, scoring, node, and schema tests:

```bash
uv run pytest tests/test_grounding.py tests/test_scoring.py tests/test_nodes.py tests/test_schemas.py
```

They verify profile-and-job provenance, alias resolution, required technology
gaps, optional and negated statements, title and tag evidence, Java versus
JavaScript boundaries, model-hallucination replacement, schema requirements,
UI evidence rendering, and score consistency.

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
live adapters run before the cache fallback. A deterministic location gate
orders eligible results and removes known geographical mismatches before
ranking runs in batches. The graph can broaden a weak search up to a fixed
limit.

See [Architecture](docs/architecture.md) for the detailed graph.

## Project structure

```text
src/job_scout/
  app.py              Gradio interface
  config.py           Environment configuration
  llm.py              Model initialization and call budget
  matching.py         Shared punctuation-safe text normalization
  profile.py          CV-to-profile extraction
  grounding.py        Evidence-backed skill matches and technology gaps
  scoring.py          Deterministic and hybrid fit-score calculation
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
