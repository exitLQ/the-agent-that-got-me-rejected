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

## 3. Install dependencies

```bash
uv sync --extra ollama --all-groups
```

On Windows, if the global uv cache is not writable:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR="$PWD\.uv-python"
uv sync --extra ollama --all-groups
```

## 4. Configure the application

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
OFFLINE_MODE=true
OPIK_ENABLED=false
```

This default uses the committed cache, disables every live job adapter, disables
Opik, and avoids external font requests from the interface. Ollama and Gradio
still communicate over the local loopback interface.

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

## 5. Verify the installation

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

## 6. Start the interface

```bash
uv run python -m job_scout.app
```

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

## 7. Development workflow

Before committing:

```bash
uv run ruff check .
uv run pytest
git status
```

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

Tracing is intentionally disabled while `OFFLINE_MODE=true`. To opt in to cloud
tracing, set `OFFLINE_MODE=false`, set `OPIK_ENABLED=true`, configure the Opik
credentials, and restart the application.

### Model authentication error

Confirm that the provider named by `SCOUT_MODEL` has a matching API key in
`.env`. Restart the application after editing the file.

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
