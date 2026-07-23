# Local-first roadmap

## Goal

Run the complete the-agent-that-got-me-rejected workflow on one machine without paid model APIs,
cloud tracing, or required network access. Live job providers remain optional.

## Target operating modes

1. Offline mode
   - Ollama provides all model inference.
   - The committed cache provides job postings.
   - Tracing is written locally.
   - No outbound network request is required.
2. Local model with live jobs
   - Ollama provides inference.
   - Keyless or configured job APIs provide current postings.
   - Cloud tracing remains disabled by default.
3. Cloud-assisted mode
   - Existing OpenAI and Opik integrations remain optional.

## Phase 1: Local model provider

- Add `langchain-ollama` as an optional dependency.
- Introduce explicit provider validation during startup.
- Add an Ollama health check with a clear error message.
- Use a configurable local default such as `ollama:llama3.2`.
- Confirm that structured output and tool calling work with the selected model.
- Add provider-specific integration tests.

Acceptance criteria:

- Profile extraction, tool selection, ranking, and reformulation complete through
  Ollama.
- The application starts without `OPENAI_API_KEY`.
- A missing Ollama service produces an actionable startup message.

## Phase 2: Strict offline job search

- Add an `OFFLINE_MODE` setting.
- Skip JSearch, Adzuna, and Remotive when offline mode is enabled.
- Make cache location configurable.
- Add cache freshness metadata and a visible stale-data notice.
- Add a deterministic local search strategy for cases where model tool calling
  is unavailable.

Acceptance criteria:

- A full run succeeds with the network disabled.
- No job adapter attempts an HTTP request in offline mode.
- Tests assert that outbound HTTP clients are never called.

## Phase 3: Local observability

- Add a no-op tracer as the default.
- Add structured JSON logs for graph nodes, latency, model calls, and errors.
- Store run metadata under a configurable local data directory.
- Add an optional local OpenTelemetry-compatible backend.
- Keep Opik as an opt-in adapter.

Acceptance criteria:

- Runs can be inspected locally without an external account.
- Logs do not contain CV text or secrets by default.
- Users can delete all run data from one documented directory.

## Phase 4: Performance and privacy

- Run independent ranking batches concurrently.
- Add model and prompt warm-up.
- Add configurable context and output limits for local hardware.
- Redact personal information from logs.
- Add a privacy mode that avoids retaining uploaded PDFs.
- Document expected RAM, CPU, and GPU requirements by model size.

Acceptance criteria:

- Ranking latency is measured before and after concurrency.
- Privacy mode leaves no CV file or raw CV text after a run.
- Resource limits fail gracefully instead of crashing the interface.

## Phase 5: Packaging

- Add one-command launch scripts for Windows, macOS, and Linux.
- Add a Docker Compose profile containing the app and Ollama.
- Add a first-run setup wizard.
- Add CI checks for offline installation, tests, and documentation.
- Publish versioned releases with migration notes.

Acceptance criteria:

- A new user can install and run the offline mode from the English setup guide.
- The Docker setup starts without cloud credentials.
- CI verifies that documentation commands remain valid.

## Recommended implementation order

1. Add `langchain-ollama` and provider checks.
2. Implement `OFFLINE_MODE`.
3. Add local structured tracing.
4. Add privacy controls.
5. Improve ranking concurrency.
6. Package and automate installation.

Each phase should include tests and a small fixture run before moving to the
next phase.
