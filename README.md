# the-agent-that-got-me-rejected

[![CI](https://github.com/exitLQ/the-agent-that-got-me-rejected/actions/workflows/ci.yml/badge.svg)](https://github.com/exitLQ/the-agent-that-got-me-rejected/actions/workflows/ci.yml)

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
- LangGraph agent with a bounded, audited search-reformulation loop
- Strict offline mode using the committed job cache by default
- Optional live search through JSearch, Adzuna, and Remotive
- Bounded concurrent job-fit ranking with a transparent hybrid score
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
PRIVACY_MODE=true
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
PRIVACY_MODE=true
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

## Optimized search reformulation

### Previous behavior

When fewer than five jobs scored at least 60, the graph asked the model for a
broader query. The following fetch node then asked the model a second time to
select search-tool arguments. That second decision could ignore the reformulated
query. In addition, old jobs were placed before new jobs and the merged list was
capped at 25, so a full first result set could discard every new retry result.

### Controlled retry flow

The graph still performs at most two reformulations, but each retry now follows
one controlled path:

1. summarize result quality without sending job descriptions;
2. request one short and materially different query;
3. validate and deduplicate the proposal;
4. choose a deterministic fallback when validation fails;
5. execute the accepted query directly without another model decision;
6. place new unique results before old results during the capped merge; and
7. rank the resulting set again.

This removes one LLM call from every retry. Ranking calls are unchanged.

### Quality feedback

The reformulation prompt receives only compact derived metadata:

- number of ranked jobs;
- number scoring at least 60;
- best score;
- up to three top job titles with scores;
- up to four common grounded technology gaps;
- the previous query; and
- all queries already attempted.

Raw job descriptions and CV text are not added to this prompt. The profile
portion contains primary roles and at most ten profile skills.

Attempt 1 asks for a common adjacent title with at most one strong skill.
Attempt 2 removes niche specialization and uses a broader established role
family.

### Query validation

`sanitize_query` accepts only the first non-empty output line and removes a
simple `Search query:` label, code fences, surrounding quotes, and a trailing
period. A proposal is rejected when it:

- is empty;
- contains more than eight whitespace-separated terms;
- exceeds 100 characters;
- contains a URL; or
- contains Boolean `AND`, `OR`, or `NOT` operators or a common prose preamble;
  or
- normalizes to a query already in history.

Duplicate detection is case-, accent-, punctuation-, and whitespace-insensitive.
For example, `Data-Scientist` and `data scientist` have the same history key.

### Deterministic fallbacks

If a model proposal is invalid or repeated, the application chooses the first
novel candidate from a fixed role map and the profile's strongest skills.
Examples include:

| Primary role | First adjacent roles |
|---|---|
| Data Scientist | Machine Learning Engineer, Data Analyst |
| Machine Learning Engineer | Data Scientist, AI Engineer |
| Data Engineer | Analytics Engineer, Platform Data Engineer |
| Software Engineer | Backend Engineer, Platform Engineer |
| Frontend Engineer | Web Developer, Full Stack Engineer |
| Product Manager | Technical Product Manager, Product Owner |

Seniority terms are removed from fallback role names. Attempt 1 prefers the
first adjacent role plus one skill. Attempt 2 prefers a different broad role
without adding another specialization. Generic technology-role queries are a
last resort, ensuring the bounded loop always has a valid novel query.

### Result merging

The merge still deduplicates by normalized title and company and still returns
at most 25 jobs. On retries, however, new unique results are ordered before old
results. This guarantees that a full initial set cannot prevent newly discovered
jobs from entering the next ranking pass.

### Query history and audit

The initial query and every executed retry query are stored in `query_history`.
Every reformulation also records:

```text
attempt
previous query
accepted query
strategy: model or fallback
acceptance or rejection reason
jobs seen
good jobs
best score
```

The result footer shows the number of executed queries and exposes their path as
hover text. Above the job cards, `Query audit` expands to show the strategy and
quality metrics for every reformulation.

### Verification

Run the optimizer, node, runner, graph, and schema tests:

```bash
uv run pytest tests/test_query_optimizer.py tests/test_nodes.py tests/test_runner.py tests/test_graph.py tests/test_schemas.py
```

They verify sanitization, duplicate keys, two deterministic fallback stages,
direct retry execution, saved model calls, new-result merge priority, diagnostic
records, query history propagation, audit rendering, loop thresholds, and
schema bounds.

## Concurrent ranking

### Execution model

Jobs are still divided into batches of five, preserving the established prompt
size and LLM-call budget. The batches are now submitted through a bounded
`ThreadPoolExecutor` instead of being invoked sequentially.

With the maximum 25 jobs:

```text
25 jobs / 5 jobs per batch = 5 ranking requests
```

The number of requests and therefore model-token use do not increase.
Concurrency overlaps request latency; it does not create additional batches.

### Configuration

The default is:

```dotenv
RANK_MAX_WORKERS=2
```

The accepted range is 1 through 8. The actual worker count for a ranking pass
is:

```text
min(RANK_MAX_WORKERS, number of batches)
```

One batch therefore uses one worker even when the setting is higher. Setting
the value to `1` restores sequential execution and provides a direct comparison
baseline.

Suggested starting values:

| Environment | Suggested workers | Reason |
|---|---:|---|
| Memory-constrained local machine | 1 | Avoid simultaneous model requests |
| Typical local Ollama setup | 2 | Default balance of overlap and resource use |
| Tested high-memory or remote model server | 3 to 4 | More overlap when the backend supports it |

Values above 4 should be used only after observing model-server memory and queue
behavior. The application caps the value at 8 to prevent accidental unbounded
fan-out.

### Deterministic aggregation

Concurrent completion order does not affect output. Every future retains its
original batch index. After all futures finish, responses are processed in
ascending batch-index order.

A separate copy of the current Python context is propagated to every worker.
This preserves LangChain callback, usage, and tracing context without attempting
to enter one shared context concurrently.

A response can contribute scores only for job identifiers belonging to its own
batch. An unexpected identifier from another batch is ignored. The existing
hybrid-score tie-break rules then determine final order independently of thread
timing.

### Failure isolation

Each batch is isolated:

- a successful batch keeps its model assessments;
- a failed batch records one concise error;
- jobs from the failed batch remain in the result set;
- those jobs use their deterministic score and the existing fallback
  explanation; and
- other batches continue normally.

Attempted failed batches still count toward `MAX_LLM_CALLS_PER_RUN`. The budget
is checked for all planned batches before any worker is submitted.

### Metrics

The result footer now reports:

```text
ranking: <batches> batches / <workers> workers / <seconds>s / <failed> failed
```

The reported ranking latency measures the model-assessment batch phase. It does
not include job fetching, deterministic scoring, evidence construction, or UI
rendering. The same fields are retained in `RunResult`:

```text
ranking_batch_count
ranking_workers
ranking_latency_s
ranking_failed_batches
```

### Measuring sequential versus concurrent ranking

Use the same CV, model, cache, and warm model process for both runs.

Sequential baseline:

```dotenv
RANK_MAX_WORKERS=1
```

Concurrent run:

```dotenv
RANK_MAX_WORKERS=2
```

Restart the application after each configuration change and compare the
`ranking` latency in the footer. Run each configuration several times because
Ollama model loading, operating-system scheduling, and backend request queues
can dominate a single measurement.

Concurrency is not guaranteed to be faster on every local machine. A backend
that serializes generation may show no improvement, while simultaneous requests
can increase memory pressure. In that case, keep `RANK_MAX_WORKERS=1`.

### Verification

Run the concurrency, node, runner, and configuration tests:

```bash
uv run pytest tests/test_concurrent_ranking.py tests/test_nodes.py tests/test_runner.py
```

The concurrency test uses a thread barrier to prove that two batches overlap
without relying on fragile wall-clock thresholds. Tests also verify sequential
mode, worker bounds, LLM-call accounting, batch-failure isolation,
cross-batch identifier isolation, deterministic-only fallback, runner metric
propagation, and footer rendering.

## Privacy mode

### What was implemented

Privacy mode is enabled by default:

```dotenv
PRIVACY_MODE=true
```

The implementation minimizes resume data at each boundary:

- the Gradio upload callback reads the temporary PDF and then immediately
  attempts to delete that temporary copy;
- deletion is allowed only below the operating system temporary directory, so
  an arbitrary source path cannot be removed;
- raw CV text exists only long enough to extract the structured `Profile`;
- raw CV text is never written to Gradio state or LangGraph checkpoint state;
- the candidate name is omitted from job-ranking prompts because it has no
  relevance to job fit;
- Opik configuration, traces, prompt registration, and PDF attachments are
  disabled while privacy mode is active; and
- the interface footer confirms that raw resume data was discarded.

The batch runner never deletes the path supplied with `--cv`. A command-line
path is treated as a user-owned original, not a Gradio temporary upload.

### Data lifecycle

| Data | During extraction | During search | After the UI callback |
|---|---|---|---|
| Temporary uploaded PDF | Read locally by `pypdf` | Not required | Deleted when inside the OS temporary tree |
| Raw extracted CV text | Passed to the configured extraction model | Not passed to LangGraph | Released and not stored in Gradio state |
| Candidate name | Extracted for the local profile card | Excluded from ranking prompts | Remains in current structured UI state |
| Structured profile | Created from the CV | Used for search and scoring | Remains until the wizard is reset |
| Ranked jobs and metrics | Not present | Produced by the graph | Remain visible in the current session |
| Cloud traces and attachments | Disabled | Disabled | Nothing is uploaded |

With the default `SCOUT_MODEL=ollama:qwen3:8b`, profile extraction is sent only
to the configured local Ollama server. Privacy mode does not convert a cloud
model into a local one. If `SCOUT_MODEL` is changed to an external provider, CV
text must be sent to that provider for extraction. Use Ollama on `localhost`
for the documented local privacy boundary.

### Interaction with offline mode and Opik

Privacy mode and offline mode are separate safeguards:

- `OFFLINE_MODE=true` prevents live job-provider calls and cloud tracing.
- `PRIVACY_MODE=true` minimizes resume retention and independently prevents
  cloud tracing and CV attachments.

Opik is active only when all of these conditions are met:

```text
OFFLINE_MODE=false
PRIVACY_MODE=false
OPIK_ENABLED=true
OPIK_API_KEY is configured
```

To intentionally use Opik, explicitly set:

```dotenv
OFFLINE_MODE=false
PRIVACY_MODE=false
OPIK_ENABLED=true
```

Disabling privacy mode does not make file deletion broader. The application
still does not delete command-line source files.

### Guarantees and limits

Privacy mode is application-level data minimization. It does not provide disk
encryption, secure erasure from solid-state storage, operating-system swap
protection, browser-cache control, malware protection, or automatic removal of
structured profile and result data shown in an active browser session. Use
full-disk encryption and a trusted local machine for sensitive resumes.

If the operating system refuses deletion because a file is locked, the helper
returns without deleting another path. The original CV selected in the browser
is not modified; Gradio supplies a temporary copy to the application.

### Verification

Run the dedicated privacy tests:

```bash
uv run pytest tests/test_privacy.py tests/test_runner.py
```

They verify the default, Opik override, absence of CV text from graph input,
both attachment guards, removal of the candidate name from ranking prompts,
temporary upload deletion, and refusal to delete paths outside the temporary
boundary.

## One-command launch

### Supported launchers

After installing the two system prerequisites, `uv` and Ollama, use one command
from the repository root.

Windows PowerShell:

```powershell
.\start.ps1
```

Linux:

```bash
./start.sh
```

macOS Terminal:

```bash
./start.command
```

On macOS, `start.command` can also be opened from Finder after its executable
permission has been preserved by Git.

The shell-specific files are intentionally small. All operating systems call
the shared `scripts/start.py` implementation, which prevents platform launch
behavior from drifting.

### First-run behavior

The default command performs these steps in order:

1. verifies that `uv` is available;
2. asks `uv` for an isolated Python 3.12 runtime for the launcher;
3. creates `.env` from `.env.example` only when `.env` does not exist;
4. installs locked dependencies with the Ollama extra and development group;
5. reads `SCOUT_MODEL` from the process environment or `.env`;
6. when the model uses Ollama, verifies the Ollama executable and service;
7. downloads the configured Ollama model only when it is missing; and
8. launches the Gradio application at <http://localhost:7860>.

An existing `.env` is never overwritten. A model configured through the process
environment takes precedence over the `.env` value. Non-Ollama models skip the
Ollama executable, service, and model checks.

Dependency synchronization is safe to repeat. `uv` reuses its environment and
lockfile, so later starts normally complete this phase quickly.

### Launcher options

Linux and macOS pass options directly:

```bash
./start.sh --check
./start.sh --skip-sync
./start.sh --skip-model-pull
```

Windows uses PowerShell switches:

```powershell
.\start.ps1 -Check
.\start.ps1 -SkipSync
.\start.ps1 -SkipModelPull
```

| Option | Behavior |
|---|---|
| `--check` or `-Check` | Performs setup and prerequisite checks, then exits without launching |
| `--skip-sync` or `-SkipSync` | Reuses the current environment without running `uv sync` |
| `--skip-model-pull` or `-SkipModelPull` | Reports the exact `ollama pull` command instead of downloading a missing model |

Use the default command for a first run. Use the skip options only after the
corresponding setup step has already succeeded.

### Failure behavior

The launcher exits with a nonzero status and an actionable message when:

- `uv` is missing;
- `.env.example` is missing while `.env` has not been created;
- dependency synchronization fails;
- an Ollama model is configured but Ollama is not installed;
- the Ollama service is not reachable;
- a required model cannot be downloaded; or
- the application exits with an error.

The launcher does not install `uv` or Ollama system-wide because those actions
require platform-specific trust and permission decisions. It links to the
official installation page instead. It also does not overwrite configuration,
API keys, or an existing virtual environment.

### Direct developer start

The lower-level command remains available when setup is already complete:

```bash
uv run python -m job_scout.app
```

The one-command launchers are the recommended user path; the direct command is
useful for debugging and development tooling.

### Verification

Run the launcher unit tests:

```bash
uv run pytest tests/test_start_script.py
```

They verify configuration creation without overwrite, environment precedence,
model-provider parsing, installed and missing model paths, service errors,
check-only operation, and that every platform wrapper delegates to the shared
launcher.

## Run the application

Use the one-command launcher for your operating system as documented above.

Open <http://localhost:7860> and upload a PDF from `data/fixture_cvs/` or your
own CV.

For detailed operating-system instructions, configuration options, and common
errors, see [Local setup](docs/local_setup.md).

## Continuous integration and quality gates

### Workflow coverage

The GitHub Actions workflow is stored at `.github/workflows/ci.yml`. It runs:

- for every push to `main`;
- for every pull request; and
- manually through `workflow_dispatch`.

When a newer commit reaches the same branch or pull request, the older workflow
run is cancelled. This avoids spending runner time on results that can no longer
be merged.

The single `Python 3.12 quality gate` job performs these steps:

1. checks out the exact commit;
2. installs `uv` and selects Python 3.12;
3. installs the project, Ollama extra, and development dependencies from
   `uv.lock`;
4. runs Ruff without modifying files;
5. runs the repository and documentation validator;
6. runs the complete offline test suite;
7. builds the Python package; and
8. verifies executable permissions for the Linux and macOS launchers.

The install and run commands use frozen lockfile behavior. A dependency change
without a corresponding `uv.lock` update therefore fails CI instead of silently
resolving a different environment.

### Network and secret boundary

Dependency and Action downloads require network access during CI setup. The
application tests themselves are configured with:

```yaml
OFFLINE_MODE: "true"
PRIVACY_MODE: "true"
OPIK_ENABLED: "false"
```

All job-provider and Opik credentials are explicitly empty. The test fixtures
mock model and network boundaries, so the workflow does not require repository
secrets and does not spend model or job-provider credits.

The workflow grants its `GITHUB_TOKEN` only `contents: read`. Checkout credential
persistence is disabled. Third-party Actions are pinned to full 40-character
commit SHAs with readable version comments, preventing a mutable version tag
from changing the executed Action code.

`.github/dependabot.yml` checks GitHub Action dependencies monthly and opens
bounded update pull requests. Each update still has to pass the complete quality
gate before merge.

### Repository validator

Run the validator directly:

```bash
uv run python scripts/check_repository.py
```

It enforces project-specific invariants that generic Python tools do not cover:

- every required configuration, license, lock, launcher, and workflow file
  exists;
- README and files under `docs/` contain no emojis;
- every relative Markdown link and image points to an existing path inside the
  repository;
- the complete sponsor block remains present exactly once;
- every external Action reference uses a full commit SHA; and
- `.env` remains untracked.

The validator prints every discovered issue in one run and returns a nonzero
exit status, making the same command suitable for local use and CI.

### Reproducing CI locally

On macOS or Linux with Make:

```bash
make check
```

The target verifies the lockfile, lints, validates the repository, runs tests,
and builds the package.

The equivalent cross-platform commands are:

```bash
uv lock --check
uv run ruff check .
uv run python scripts/check_repository.py
uv run pytest
uv build
```

CI itself adds `--frozen` to installation and execution commands. Locally,
`uv lock --check` first gives a clearer error when `pyproject.toml` and
`uv.lock` disagree.

### Branch protection

After the workflow has completed once on GitHub, repository maintainers can
protect `main` and require the `Python 3.12 quality gate` status check before
merge. Branch protection is a GitHub repository setting and is intentionally
not changed by this code commit.

### Failure guide

| Failed step | Typical cause | Local command |
|---|---|---|
| Install locked dependencies | `pyproject.toml` changed without updating `uv.lock` | `uv lock --check` |
| Lint | Import order, style, or static error | `uv run ruff check .` |
| Validate repository and documentation | Broken link, emoji, sponsor change, unpinned Action, or tracked `.env` | `uv run python scripts/check_repository.py` |
| Run offline test suite | Behavioral regression or external-call boundary violation | `uv run pytest` |
| Build package | Invalid package metadata or missing source file | `uv build` |
| Verify launcher permissions | Executable bit lost from a shell launcher | `git update-index --chmod=+x start.sh start.command` |

### Verification

Run only the CI policy tests:

```bash
uv run pytest tests/test_repository_checks.py
```

These tests prove that the current repository passes the validator, the
workflow uses frozen and offline settings, Actions are SHA-pinned, the sponsor
block is intact, documentation is emoji-free, and local links resolve.

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
  query_optimizer.py  Query validation, history, and deterministic fallbacks
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
scripts/
  check_repository.py Repository and documentation policy checks
  start.py            Shared cross-platform setup and launch logic
  ...                 Batch and data-maintenance utilities
start.ps1             Windows one-command launcher
start.sh              Linux one-command launcher
start.command         macOS one-command launcher
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
| `RANK_MAX_WORKERS` | Maximum concurrent ranking requests, from 1 to 8 | No |
| `OFFLINE_MODE` | Restricts job search and tracing to local resources | No |
| `PRIVACY_MODE` | Minimizes CV retention and disables cloud tracing | No |
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
