# Contributing

Thank you for considering a contribution to
`the-agent-that-got-me-rejected`. Contributions should preserve the project's
local-first defaults, privacy boundary, deterministic fallbacks, and
evidence-backed job matching.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Security vulnerabilities must follow the private process in
[SECURITY.md](SECURITY.md), not the public issue tracker.

## Before opening an issue

1. Search existing issues and pull requests for the same problem.
2. Confirm the problem still occurs on the latest `main` branch.
3. Remove API keys, resume content, personal data, and access tokens.
4. Use the appropriate bug or feature issue form.
5. Include the smallest reproducible example when reporting a bug.

General setup questions belong in a GitHub Discussion when Discussions are
enabled. A focused documentation improvement may be submitted directly as a
pull request.

## Development setup

Requirements:

- Python 3.12
- `uv`
- Git
- Ollama and the configured local model for manual application testing

Clone and install all locked development dependencies:

```bash
git clone https://github.com/exitLQ/the-agent-that-got-me-rejected.git
cd the-agent-that-got-me-rejected
uv sync --all-extras --all-groups
```

Copy `.env.example` to `.env`. Keep the default offline and privacy settings
unless the change explicitly requires an online provider. Never commit `.env`
or a real credential.

Run the application:

```bash
uv run python -m job_scout.app
```

## Making a change

1. Create a focused branch from the latest `main`.
2. Keep the change limited to one problem or feature.
3. Add or update tests for observable behavior.
4. Update English documentation when configuration, behavior, or commands
   change.
5. Keep documentation free of emojis.
6. Do not modify the sponsor block in `README.md`.
7. Do not add scraping integrations for sites that prohibit automated access.
8. Preserve offline mode, privacy mode, explicit cloud consent, and secret
   handling.

## Code standards

- Target Python 3.12.
- Follow the Ruff configuration in `pyproject.toml`.
- Prefer typed, testable functions and explicit error messages.
- Keep external network boundaries injectable or mockable in tests.
- Do not log secrets, raw resume text, or unnecessary personal data.
- Avoid unrelated formatting or dependency changes.
- Keep provider-specific behavior behind the shared model abstraction.

## Required checks

Run the same checks used by CI:

```bash
uv lock --check
uv run ruff check .
uv run python scripts/check_repository.py
uv run pytest
uv build
```

All checks must pass without using real API keys or paid external calls.

## Pull requests

Use the pull request template and provide:

- the problem and the chosen solution;
- user-visible and privacy implications;
- the tests that were run;
- documentation changes; and
- any remaining limitations or follow-up work.

Keep commits understandable and avoid committing generated caches, local
reports, build artifacts, or editor files. A maintainer may request changes,
additional tests, documentation, or a smaller scope before merging.

## Licensing

By submitting a contribution, you agree that it may be distributed under the
repository's [MIT License](LICENSE).
