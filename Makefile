.DEFAULT_GOAL := help

# Self-documenting help: any target with a `## comment` is listed.
.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Install deps and pre-commit hooks
	uv sync --all-groups
	uv run pre-commit install

.PHONY: app
app: ## Launch the Gradio app
	uv run python -m job_scout.app

.PHONY: batch
batch: ## Run the baseline batch (prompts for --yes cost confirmation)
	uv run python scripts/run_batch.py

.PHONY: snapshot
snapshot: ## Rebuild data/cached_jobs.json from live sources
	uv run python scripts/snapshot_jobs.py

.PHONY: fixtures
fixtures: ## Regenerate the synthetic fixture CV PDFs
	uv run python scripts/generate_fixture_cvs.py

.PHONY: test
test: ## Run the test suite
	uv run pytest

.PHONY: lint
lint: ## Lint with ruff
	uv run ruff check .

.PHONY: format
format: ## Format with ruff
	uv run ruff format .
	uv run ruff check --fix .
