"""Strict offline-mode behaviour."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from job_scout.app import CSS, THEME
from job_scout.config import Settings
from job_scout.tools.jobs_api import CacheSource, run_search


def test_offline_mode_uses_only_cache():
    external_sources = [MagicMock(), MagicMock(), MagicMock()]
    cache = MagicMock()
    cache.fetch.return_value = []

    jobs, used = run_search(
        "python",
        jsearch=external_sources[0],
        adzuna=external_sources[1],
        remotive=external_sources[2],
        cache=cache,
        offline_mode=True,
    )

    assert jobs == []
    assert used == []
    cache.fetch.assert_called_once()
    for source in external_sources:
        source.fetch.assert_not_called()


def test_offline_mode_performs_no_job_http_requests(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Offline job search attempted an HTTP request")

    monkeypatch.setattr(httpx, "get", fail_if_called)
    jobs, used = run_search("python", offline_mode=True)
    assert jobs
    assert used == ["cache"]


def test_offline_mode_disables_opik_even_with_credentials():
    settings = Settings(
        _env_file=None,
        OFFLINE_MODE=True,
        OPIK_ENABLED=True,
        OPIK_API_KEY="configured-but-disabled",
    )
    assert settings.has_opik is False


def test_cache_metadata_is_available():
    metadata = CacheSource().metadata()
    assert metadata["job_count"] > 0
    assert metadata["modified_date"] != "unknown"


def test_ui_css_has_no_external_font_import():
    assert "fonts.googleapis.com" not in CSS
    assert "@import url(" not in CSS
    assert THEME._stylesheets == []
