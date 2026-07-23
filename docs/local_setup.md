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
OPIK_ENABLED=false
```

Optional live job sources:

```dotenv
JSEARCH_API_KEY=
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
```

When these values are empty, the-agent-that-got-me-rejected uses the keyless Remotive adapter and the
offline cache.

## 5. Verify the installation

```bash
uv run pytest
uv run ruff check .
```

The automated tests mock model and network calls and should not consume API
credits.

## 6. Start the interface

```bash
uv run python -m job_scout.app
```

Open <http://localhost:7860>.

Use a synthetic PDF from `data/fixture_cvs/` for the first run. The application
extracts the profile first and then starts the job-search graph.

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

This is expected when live-source credentials are not configured or a provider
is unavailable. Cached results keep the application usable for development.

### No traces appear

Tracing is optional. Set `OPIK_ENABLED=true` and configure the Opik credentials
only when external observability is desired.

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
