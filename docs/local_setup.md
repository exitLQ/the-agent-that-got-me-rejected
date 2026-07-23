# Local setup

This guide explains how to install and run the-agent-that-got-me-rejected on a development machine.

## 1. Install prerequisites

Install:

- Git
- Python 3.12
- uv
- Ollama

Confirm the tools are available:

```bash
git --version
uv --version
```

The project requires Python 3.12. `uv` downloads an isolated compatible Python
version when necessary.

## 2. Clone the repository

```bash
git clone https://github.com/exitLQ/the-agent-that-got-me-rejected.git
cd the-agent-that-got-me-rejected
```

## 3. Use the one-command launcher

After installing `uv` and Ollama, the recommended path performs dependency
setup, configuration creation, model validation, and application startup.

Windows PowerShell:

```powershell
.\start.ps1
```

Linux:

```bash
./start.sh
```

macOS:

```bash
./start.command
```

The first run can download the configured Ollama model and may take longer.
Subsequent runs reuse the environment and installed model.

Use check-only mode to prepare and validate without starting Gradio:

```powershell
.\start.ps1 -Check
```

```bash
./start.sh --check
```

The launcher creates `.env` only when it is absent. It never overwrites an
existing configuration. See the README launcher section for all skip options
and failure behavior.

## 4. Manual dependency installation

The following manual commands remain available for development or launcher
troubleshooting.

```bash
uv sync --extra ollama --all-groups
```

On Windows, if the global uv cache is not writable:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR="$PWD\.uv-python"
uv sync --extra ollama --all-groups
```

To install Ollama and every supported cloud-provider integration:

```bash
uv sync --all-extras --all-groups
```

## 5. Configure the application

Create `.env` from the example:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Pull the default model:

```bash
ollama pull qwen3:8b
```

Minimal local model configuration:

```dotenv
SCOUT_MODEL=ollama:qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
RANK_MAX_WORKERS=2
OFFLINE_MODE=true
PRIVACY_MODE=true
CLOUD_LLM_ENABLED=false
OPIK_ENABLED=false
```

This default uses the committed cache, disables every live job adapter, disables
Opik, and avoids external font requests from the interface. Ollama and Gradio
still communicate over the local loopback interface.

Privacy mode is a separate default safeguard:

```dotenv
PRIVACY_MODE=true
```

It deletes eligible Gradio temporary uploads after reading, keeps raw CV text
out of Gradio and LangGraph state, omits the candidate name from ranking
prompts, and disables Opik traces and attachments. The structured profile and
ranked results remain in the current browser session until reset.

For the strongest documented local boundary, combine privacy mode with
`OFFLINE_MODE=true`, an Ollama model, and `OLLAMA_BASE_URL` on `localhost`.
Privacy mode cannot prevent an explicitly configured cloud model from receiving
the resume text required for profile extraction. The batch command preserves
the user-owned PDF path; automatic deletion applies only to UI files inside the
operating system temporary directory.

### Optional cloud model

Cloud models require an explicit three-part configuration: disable strict
offline mode, enable cloud-LLM consent, and provide the key matching the model
prefix.

OpenAI:

```dotenv
SCOUT_MODEL=openai:gpt-5-mini
OFFLINE_MODE=false
CLOUD_LLM_ENABLED=true
OPENAI_API_KEY=your-key
```

Anthropic:

```dotenv
SCOUT_MODEL=anthropic:claude-sonnet-4-6
OFFLINE_MODE=false
CLOUD_LLM_ENABLED=true
ANTHROPIC_API_KEY=your-key
```

Grok from xAI:

```dotenv
SCOUT_MODEL=xai:grok-4.3
OFFLINE_MODE=false
CLOUD_LLM_ENABLED=true
XAI_API_KEY=your-key
```

Grok is not Groq. Groq uses the separate `groq:` prefix and `GROQ_API_KEY`.
When a cloud provider is active, raw CV text is sent to that provider during
profile extraction. Privacy mode still minimizes local retention and disables
Opik, but it cannot make remote inference local. The interface displays this
boundary before a CV is uploaded.

Because `OFFLINE_MODE=false` is the global network opt-in, it also enables the
live job-source cascade. With no job-source keys, the application can call the
keyless Remotive adapter before falling back to the cache.

Optional live job sources require explicit online mode:

```dotenv
OFFLINE_MODE=false
JSEARCH_API_KEY=
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
```

When `OFFLINE_MODE=false`, the-agent-that-got-me-rejected tries configured
providers, the keyless Remotive service, and then the cache. Empty provider keys
do not restore strict offline behavior; use `OFFLINE_MODE=true` for that
guarantee.

## 6. Verify the installation

```bash
uv run pytest
uv run ruff check .
```

The automated tests mock model and network calls and should not consume API
credits.

Verify strict offline behavior separately:

```bash
uv run pytest tests/test_offline_mode.py
```

Verify the shared launcher separately:

```bash
uv run pytest tests/test_start_script.py
```

## 7. Start the interface manually

```bash
uv run python -m job_scout.app
```

Prefer the operating-system launcher in section 3 for normal use.

Open <http://localhost:7860>.

Use a synthetic PDF from `data/fixture_cvs/` for the first run. The application
extracts the profile first and then starts the job-search graph.

### Location behavior

The locations extracted from the CV control a deterministic post-filter:

- exact city matches appear first;
- geographically eligible remote roles appear next when remote work is
  accepted;
- other jobs in the same country are fallback results; and
- known country or remote-scope mismatches are removed.

Location matching ignores case, accents, and punctuation. It also recognizes
common translations such as `Munich` and `München`. Unknown locations are not
assigned to a guessed country.

### Reading the fit score

The large score on each job card is a hybrid:

```text
60% deterministic rules + 40% model assessment
```

The rule score combines skills, role, seniority, and location. The card lists
all component values below the explanation. This makes differences between two
results inspectable and helps identify incomplete CV or job data.

### Reading skill evidence

The matched-skill and gap chips are validated locally. Expand `Skill evidence`
on a result card to inspect:

- the exact `profile.skills` entry supporting a match;
- the title, tag, or description excerpt supporting the job-side claim; and
- confirmation that a displayed gap is absent from the profile.

Optional or negated technologies are not shown as gaps. If a relevant
technology is missing, the job may use an alias not yet present in the controlled
catalog or may describe it without a clear requirement cue.

### Reading the query audit

When the first search returns fewer than five jobs scoring at least 60, the
agent may broaden the query up to two times. Expand `Query audit` above the
result cards to inspect:

- every executed query;
- whether the model proposal or deterministic fallback was used;
- why a fallback was necessary; and
- the job count, good-job count, and best score before each retry.

The footer also shows the total query count. Repeated, overly long, empty, or
URL-containing model output is rejected automatically.

### Ranking concurrency

Ranking uses batches of five jobs and up to two concurrent model requests by
default. The footer reports batch count, worker count, ranking latency, and
failed batches.

If Ollama consumes too much memory, configure:

```dotenv
RANK_MAX_WORKERS=1
```

To test whether concurrency helps on your machine, run the same CV once with
`RANK_MAX_WORKERS=1` and again with `RANK_MAX_WORKERS=2`, restarting the app
between runs. Compare the ranking-only footer latency rather than total runtime.

## 8. Development workflow

Before committing:

```bash
uv lock --check
uv run ruff check .
uv run python scripts/check_repository.py
uv run pytest
uv build
git status
```

On macOS or Linux, the same quality sequence is available as:

```bash
make check
```

These commands reproduce the GitHub Actions quality gate. The repository
validator checks required files, documentation links, the no-emoji rule, the
sponsor block, immutable Action pins, and that `.env` is not tracked.

Commit and push:

```bash
git add .
git commit -m "Describe the change"
git push origin main
```

## Troubleshooting

### Python version mismatch

Run:

```bash
uv python install 3.12
uv sync --python 3.12 --all-groups
```

The normal launcher requests Python 3.12 from `uv` automatically. These manual
commands are primarily useful when debugging an existing environment.

### Launcher cannot find uv

Install `uv` from
<https://docs.astral.sh/uv/getting-started/installation/>, open a new terminal,
and confirm:

```bash
uv --version
```

Then run the launcher again.

### Launcher cannot reach Ollama

Start the Ollama application or service, then run:

```bash
ollama list
```

The launcher checks the same command before starting the application. If the
configured model is absent, the default launcher downloads it. Use
`--skip-model-pull` on Linux or macOS, or `-SkipModelPull` on Windows, to receive
the manual pull command instead.

### No live jobs

Live jobs are intentionally disabled while `OFFLINE_MODE=true`. Set
`OFFLINE_MODE=false` and restart the application to opt in to live providers.
Cached results keep the application usable without them. The interface shows
the cache count and file date because cached listings can be stale.

### No jobs for the selected location

The cache may contain no keyword match in the requested city, country, or
eligible remote region. Check the extracted locations on the profile screen.
Use a city-and-country form such as `Vienna, Austria` when editing the source CV.
With online mode enabled, also confirm that the provider supports that country.

### No traces appear

Tracing is intentionally disabled while `OFFLINE_MODE=true` or
`PRIVACY_MODE=true`. To opt in to cloud tracing, set both values to `false`, set
`OPIK_ENABLED=true`, configure the Opik credentials, and restart the
application.

### Model authentication error

Confirm that the provider named by `SCOUT_MODEL` has a matching API key in
`.env`. Also confirm `OFFLINE_MODE=false` and `CLOUD_LLM_ENABLED=true`. Restart
the application after editing the file.

### Cloud model is blocked at startup

This is intentional unless external data transfer has been explicitly enabled.
Check the provider prefix and use exactly one matching key:

| Prefix | Key |
|---|---|
| `openai:` | `OPENAI_API_KEY` |
| `anthropic:` | `ANTHROPIC_API_KEY` |
| `xai:` | `XAI_API_KEY` |
| `groq:` | `GROQ_API_KEY` |

If the CV must remain local, keep `OFFLINE_MODE=true`,
`CLOUD_LLM_ENABLED=false`, and select an `ollama:` model instead.

### Ollama is not reachable

Start Ollama and verify:

```bash
curl http://localhost:11434/api/tags
```

If the configured model is missing:

```bash
ollama pull qwen3:8b
```

### Port 7860 is in use

Stop the existing process that uses the port, or change the Gradio launch
configuration in `src/job_scout/app.py`.

### GitHub Actions fails during dependency installation

Run:

```bash
uv lock --check
```

If the lockfile is outdated, regenerate it intentionally with `uv lock`, inspect
the change, and rerun the complete local quality sequence. CI uses frozen
installation and will not repair an outdated lockfile automatically.

### GitHub Actions fails repository validation

Run:

```bash
uv run python scripts/check_repository.py
```

The command reports every broken documentation link, emoji, required-file
problem, sponsor-block change, unpinned Action, or tracked `.env` in one pass.
