"""Regression checks for explicitly patched development dependencies."""

from __future__ import annotations

import re
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
LOCK_TEXT = (ROOT / "uv.lock").read_text(encoding="utf-8")


def _locked_version(package: str) -> Version:
    match = re.search(
        rf'(?ms)^\[\[package]]\s+name = "{re.escape(package)}"\s+version = "([^"]+)"',
        LOCK_TEXT,
    )
    assert match, f"{package} is missing from uv.lock"
    return Version(match.group(1))


def test_jupyterlab_lock_excludes_july_2026_advisories():
    assert _locked_version("jupyterlab") >= Version("4.6.2")


def test_pytest_lock_excludes_insecure_tmpdir_versions():
    assert _locked_version("pytest") >= Version("9.0.3")
