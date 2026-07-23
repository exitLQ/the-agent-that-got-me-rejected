"""Local and CI checks for repository documentation and security invariants."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

SPONSOR_BLOCK = """<!-- hypertribe:sponsors:start -->
## Sponsors

[![the-agent-that-got-me-rejected Sponsors](https://api.tribe.run/tokens/GitYLyzVihz9dXk5QJkML4bcRn2s1qZ996BHZK7TvrKd/sponsors.svg)](https://tribe.run/token/GitYLyzVihz9dXk5QJkML4bcRn2s1qZ996BHZK7TvrKd)

Become a sponsor on [Tribe.run](https://tribe.run/token/GitYLyzVihz9dXk5QJkML4bcRn2s1qZ996BHZK7TvrKd).
<!-- hypertribe:sponsors:end -->"""

EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"
    "\u2600-\u27bf"
    "]"
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
ACTION_USE = re.compile(r"^\s*uses:\s*[^@\s]+@([^\s#]+)", re.MULTILINE)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
PACKAGE_VERSION = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)


def markdown_files() -> list[Path]:
    """Return user-facing Markdown files governed by the documentation policy."""
    return [README, *sorted((ROOT / "docs").rglob("*.md"))]


def check_no_emojis() -> list[str]:
    """Require emoji-free README and documentation."""
    errors = []
    for path in markdown_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if EMOJI.search(line):
                errors.append(f"{path.relative_to(ROOT)}:{line_number}: emoji is not allowed")
    return errors


def check_local_markdown_links() -> list[str]:
    """Require every relative Markdown link and image target to exist."""
    errors = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            raw_target = match.group(1).strip()
            target = raw_target.split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            file_part = unquote(target.split("#", 1)[0])
            resolved = (path.parent / file_part).resolve()
            if not resolved.is_relative_to(ROOT) or not resolved.exists():
                line_number = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{path.relative_to(ROOT)}:{line_number}: missing local link target {target}"
                )
    return errors


def check_sponsor_block() -> list[str]:
    """Protect the exact sponsor block requested by the maintainer."""
    text = README.read_text(encoding="utf-8")
    if text.count("<!-- hypertribe:sponsors:start -->") != 1:
        return ["README.md: sponsor start marker must occur exactly once"]
    if text.count("<!-- hypertribe:sponsors:end -->") != 1:
        return ["README.md: sponsor end marker must occur exactly once"]
    if SPONSOR_BLOCK not in text:
        return ["README.md: required sponsor block changed or is incomplete"]
    return []


def check_required_files() -> list[str]:
    """Require launch, configuration, community, license, lock, and workflow files."""
    required = [
        ".env.example",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "README.md",
        "SECURITY.md",
        "pyproject.toml",
        "uv.lock",
        ".github/dependabot.yml",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/pull_request_template.md",
        ".github/workflows/ci.yml",
        "scripts/start.py",
        "start.ps1",
        "start.sh",
        "start.command",
    ]
    return [f"{item}: required repository file is missing" for item in required if not (ROOT / item).is_file()]


def check_action_pins() -> list[str]:
    """Require immutable full-SHA pins for every third-party workflow action."""
    if not WORKFLOW.exists():
        return [".github/workflows/ci.yml: workflow is missing"]
    uses = ACTION_USE.findall(WORKFLOW.read_text(encoding="utf-8"))
    if not uses:
        return [".github/workflows/ci.yml: no actions were found"]
    return [
        f".github/workflows/ci.yml: action ref {ref!r} is not a full commit SHA"
        for ref in uses
        if not FULL_SHA.fullmatch(ref)
    ]


def check_version_sync() -> list[str]:
    """Keep package metadata, runtime metadata, and release documentation aligned."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = project["project"]["version"]
    package_text = (ROOT / "src" / "job_scout" / "__init__.py").read_text(encoding="utf-8")
    package_match = PACKAGE_VERSION.search(package_text)
    package_version = package_match.group(1) if package_match else ""
    errors = []
    if package_version != project_version:
        errors.append(
            "src/job_scout/__init__.py: __version__ must match pyproject.toml "
            f"({package_version!r} != {project_version!r})"
        )
    if f"## Version {project_version}" not in README.read_text(encoding="utf-8"):
        errors.append(f"README.md: missing release section for version {project_version}")
    return errors


def check_private_files_untracked() -> list[str]:
    """Require local credentials and tracker databases to remain untracked."""
    targets = {
        ".env": "secret-bearing local configuration",
        "data/applications.db": "local application data",
        "data/applications.db-shm": "local SQLite application data",
        "data/applications.db-wal": "local SQLite application data",
    }
    errors = []
    for path, description in targets.items():
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            errors.append(f"{path}: {description} must not be tracked")
    return errors


def collect_errors() -> list[str]:
    """Run all repository invariants and return stable, printable failures."""
    checks = (
        check_required_files,
        check_no_emojis,
        check_local_markdown_links,
        check_sponsor_block,
        check_action_pins,
        check_version_sync,
        check_private_files_untracked,
    )
    return [error for check in checks for error in check()]


def main() -> int:
    """Print all violations and return a CI-compatible exit status."""
    errors = collect_errors()
    if errors:
        print("Repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
