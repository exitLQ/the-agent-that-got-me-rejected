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


def test_shared_test_fixture_keeps_the_ci_baseline_offline():
    conftest = (checks.ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")

    assert 'os.environ["SCOUT_MODEL"] = "ollama:qwen3:8b"' in conftest
    assert 'os.environ["OFFLINE_MODE"] = "true"' in conftest
    assert 'os.environ["PRIVACY_MODE"] = "true"' in conftest
    assert 'os.environ["CLOUD_LLM_ENABLED"] = "false"' in conftest


def test_required_community_health_files_are_present():
    required = [
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/pull_request_template.md",
    ]

    assert all((checks.ROOT / path).is_file() for path in required)


def test_issue_forms_have_required_github_metadata():
    templates = [
        checks.ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
        checks.ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
    ]

    for template in templates:
        text = template.read_text(encoding="utf-8")
        assert text.startswith("name:")
        assert "\ndescription:" in text
        assert "\nbody:" in text


def test_every_workflow_action_is_pinned_to_full_sha():
    assert checks.check_action_pins() == []


def test_version_metadata_and_release_documentation_match():
    assert checks.check_version_sync() == []


def test_sponsor_block_is_preserved():
    assert checks.check_sponsor_block() == []


def test_markdown_has_no_emojis_or_broken_local_links():
    assert checks.check_no_emojis() == []
    assert checks.check_local_markdown_links() == []
