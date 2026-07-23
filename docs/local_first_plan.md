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

Status: implemented.

- Added `langchain-ollama` as an optional dependency.
- Added explicit provider validation during startup.
- Added an Ollama health check with clear error messages.
- Set `ollama:qwen3:8b` as the configurable local default.
- Reused the existing structured-output and tool-calling interfaces.
- Added provider-specific integration tests with a mocked Ollama endpoint.

Acceptance criteria:

- Profile extraction, tool selection, ranking, and reformulation complete through
  Ollama.
- The application starts without `OPENAI_API_KEY`.
- A missing Ollama service produces an actionable startup message.

## Phase 2: Strict offline job search

Status: implemented.

- Added `OFFLINE_MODE=true` as the default.
- Made offline search return directly from the committed cache without
  initializing or calling JSearch, Adzuna, or Remotive.
- Disabled Opik automatically in offline mode, including when credentials are
  configured.
- Removed the external Google Fonts import from the interface.
- Added cache count and file-date metadata to a visible stale-data notice.
- Added tests that fail if a live adapter or job-search HTTP client is called.

Acceptance criteria:

- A full run uses local Ollama and the committed job cache.
- No live job adapter attempts an HTTP request in offline mode.
- Dedicated tests assert the local-only boundary.

Implementation note: making the cache path configurable and adding a
model-independent query generator remain possible refinements. They are not
required for the strict network boundary because cache search is already
deterministic after the model supplies the query.

## Incremental improvement 3: Precise location matching

Status: implemented.

- Added accent-, case-, whitespace-, and punctuation-insensitive normalization.
- Replaced the implicit United States fallback with validated country
  resolution.
- Added exact-city, remote-region, same-country, and mismatch levels.
- Added translated city aliases and word-boundary-safe country aliases.
- Applied the same deterministic filter to cache and live-source results.
- Made the search consider every preferred location extracted from a profile.
- Made the primary profile location authoritative over an inconsistent
  model-selected country.
- Added tests for local, country, remote, multiple-location, unknown-location,
  and provider cases.

Acceptance criteria:

- A Berlin preference ranks Berlin above eligible European remote work and
  same-country fallbacks.
- A country-restricted remote role is excluded for candidates outside that
  country.
- Unknown place names do not silently trigger a United States request.
- Location behavior is identical in offline and online result processing.

## Incremental improvement 4: Deterministic hybrid score

Status: implemented.

- Replaced direct display of the model score with a fixed 60% rules and 40%
  model formula.
- Added weighted skill, role, seniority, and location components.
- Added punctuation-safe normalization for common technical skills.
- Preserved jobs omitted from a model batch by falling back to their
  deterministic score.
- Added an explicit four-step tie-break order.
- Exposed every component in the result cards.
- Added unit tests for formula values, boundaries, normalization, inflated
  model assessments, and incomplete model responses.

Acceptance criteria:

- The same component inputs always produce the same final score.
- A high model score cannot by itself turn a clearly unrelated job into a
  strong match.
- Every displayed score can be reconstructed from documented values.
- A malformed partial model response does not silently remove a fetched job.

## Incremental improvement 5: Skill grounding

Status: implemented.

- Replaced direct display of model skill claims with deterministic evidence
  resolution.
- Required both profile-side and job-side provenance for matched skills.
- Required job-side requirement evidence and profile absence for skill gaps.
- Added canonical aliases for common languages, frameworks, cloud platforms,
  data tools, and infrastructure tools.
- Excluded optional and negated requirements from gaps.
- Reused the grounded match set in the hybrid score's skill component.
- Added expandable evidence to each result card.
- Added tests for aliases, provenance, hallucinated claims, requirement cues,
  negation, punctuation, schemas, UI rendering, and scoring consistency.

Acceptance criteria:

- No displayed matched skill exists only in the model response.
- Every displayed match points to both a profile entry and job evidence.
- Every displayed gap points to job requirement evidence and confirms profile
  absence.
- Alias spelling differences do not create duplicate or contradictory results.
- Skill chips and the numeric skill component use the same match set.

## Incremental improvement 6: Optimized search reformulation

Status: implemented.

- Added compact result diagnostics to the reformulation prompt.
- Added attempt-specific broadening instructions.
- Added query sanitization, length limits, and normalized duplicate detection.
- Added deterministic role-family fallbacks.
- Executed accepted retry queries directly, removing one model call per retry.
- Changed capped retry merging to prioritize new unique jobs.
- Added query history and structured reformulation audit records.
- Exposed the audit and query count in the interface.
- Added tests for validation, history, fallbacks, diagnostics, call savings,
  merge behavior, runner propagation, UI rendering, and schema bounds.

Acceptance criteria:

- A retry cannot repeat a previous query after normalization.
- Invalid model output always produces a valid deterministic fallback.
- The accepted retry query cannot be replaced by a second model decision.
- New retry results can enter a full 25-job result set.
- Every broadening decision is inspectable after the run.

## Incremental improvement 7: Concurrent ranking

Status: implemented.

- Added bounded concurrent execution for five-job ranking batches.
- Added `RANK_MAX_WORKERS` with a validated range of 1 through 8 and a default
  of 2.
- Preserved deterministic aggregation by original batch index.
- Restricted each response to identifiers from its own batch.
- Isolated batch failures and retained affected jobs with deterministic scores.
- Preserved preflight LLM-budget enforcement and attempted-call accounting.
- Added ranking batch, worker, latency, and failure metrics to state, runner,
  and the UI footer.
- Added tests proving real overlap, sequential mode, failure isolation, worker
  bounds, metrics, and footer rendering.

Acceptance criteria:

- At least two independent batches can be in flight simultaneously.
- Completion order cannot change final aggregation.
- One failed batch does not remove jobs or cancel successful batches.
- Users can switch to sequential mode on constrained hardware.
- Sequential and concurrent ranking latency can be compared from the UI.

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

Status: implemented for ranking concurrency and resume privacy.

- Run independent ranking batches concurrently.
- Add model and prompt warm-up.
- Add configurable context and output limits for local hardware.
- Omit the candidate name from job-ranking prompts.
- Add a default privacy mode that removes temporary UI uploads.
- Keep raw CV text out of Gradio and LangGraph state.
- Disable Opik traces and PDF attachments in privacy mode.
- Document expected RAM, CPU, and GPU requirements by model size.

Acceptance criteria:

- Ranking latency is measured before and after concurrency.
- Privacy mode removes eligible temporary CV uploads and retains no raw CV text
  in application state after profile extraction.
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
