"""Tests for repository-level CI and documentation invariants."""

from __future__ import annotations

import scripts.check_repository as checks


def test_repository_quality_gate_passes():
    assert checks.collect_errors() == []


def test_ci_uses_frozen_lockfile_and_offline_defaults():
    workflow = checks.WORKFLOW.read_text(encoding="utf-8")

    assert "uv sync --frozen" in workflow
    assert "uv run --frozen pytest" in workflow
    assert 'OFFLINE_MODE: "true"' in workflow
    assert 'PRIVACY_MODE: "true"' in workflow
    assert 'CLOUD_LLM_ENABLED: "false"' in workflow
    assert 'OPIK_ENABLED: "false"' in workflow
    assert "permissions:\n  contents: read" in workflow


def test_every_workflow_action_is_pinned_to_full_sha():
    assert checks.check_action_pins() == []


def test_sponsor_block_is_preserved():
    assert checks.check_sponsor_block() == []


def test_markdown_has_no_emojis_or_broken_local_links():
    assert checks.check_no_emojis() == []
    assert checks.check_local_markdown_links() == []
