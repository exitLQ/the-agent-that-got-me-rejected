"""Jobs tool: adapter behaviour, fallback ordering, dedupe/cap."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from job_scout.tools.jobs_api import (
    AdzunaSource,
    CacheSource,
    JSearchSource,
    location_match_rank,
    location_to_country,
    normalize_country_code,
    normalize_location,
    run_search,
)
from tests.conftest import make_job


def _fake_source(name, jobs):
    src = MagicMock()
    src.name = name
    src.fetch.return_value = jobs
    return src


def test_location_to_country_mapping():
    assert location_to_country("Berlin, Germany") == "de"
    assert location_to_country("San Francisco, USA") == "us"
    assert location_to_country("Bengaluru, India") == "in"
    assert location_to_country("Sydney") == "au"
    assert location_to_country("Vienna, Austria") == "at"
    assert location_to_country("Australia") == "au"  # "us" is not a substring match
    assert location_to_country("Atlantis") is None
    assert location_to_country(None) is None


def test_location_normalization_and_country_validation():
    assert normalize_location("  MÜNCHEN, Deutschland ") == "munchen deutschland"
    assert normalize_country_code("DE") == "de"
    assert normalize_country_code("Germany") == "de"
    assert normalize_country_code("invalid") is None


def test_location_match_ranks_exact_country_and_mismatch():
    exact = location_match_rank(
        "Mitte, Berlin",
        "Berlin, Germany",
        None,
        job_remote=False,
        remote_requested=False,
    )
    translated = location_match_rank(
        "München, Deutschland",
        "Munich, Germany",
        None,
        job_remote=False,
        remote_requested=False,
    )
    same_country = location_match_rank(
        "Essen, Nordrhein-Westfalen",
        "Berlin, Germany",
        None,
        job_remote=False,
        remote_requested=False,
    )
    mismatch = location_match_rank(
        "London, UK",
        "Berlin, Germany",
        None,
        job_remote=False,
        remote_requested=False,
    )

    assert exact == 4
    assert translated == 4
    assert same_country == 2
    assert mismatch == 0


def test_remote_location_scope_must_include_candidate_country():
    worldwide = location_match_rank(
        "Worldwide",
        "Berlin, Germany",
        None,
        job_remote=True,
        remote_requested=True,
    )
    europe = location_match_rank(
        "Europe only",
        "Vienna, Austria",
        None,
        job_remote=True,
        remote_requested=True,
    )
    us_only = location_match_rank(
        "USA only",
        "Berlin, Germany",
        None,
        job_remote=True,
        remote_requested=True,
    )
    multi_country = location_match_rank(
        "USA, Canada, USA timezones",
        "New York, USA",
        None,
        job_remote=True,
        remote_requested=True,
    )

    assert worldwide == 3
    assert europe == 3
    assert us_only == 0
    assert multi_country == 3


def test_offline_results_are_filtered_and_exact_location_comes_first():
    cache = _fake_source(
        "cache",
        [
            make_job("de-other", "Data Scientist", "Essen Co"),
            make_job("gb", "Data Scientist", "London Co"),
            make_job("exact", "Data Scientist", "Berlin Co"),
            make_job("global", "Data Scientist", "Remote Co", remote=True),
        ],
    )
    cache.fetch.return_value[0].location = "Essen, Deutschland"
    cache.fetch.return_value[1].location = "London, UK"
    cache.fetch.return_value[2].location = "Berlin, Deutschland"
    cache.fetch.return_value[3].location = "Worldwide"

    jobs, used = run_search(
        "data scientist",
        location="Berlin, Germany",
        remote=True,
        cache=cache,
        offline_mode=True,
    )

    assert [job.job_id for job in jobs] == ["exact", "global", "de-other"]
    assert used == ["cache"]


def test_all_profile_locations_are_considered():
    cache = _fake_source(
        "cache",
        [
            make_job("vienna", "Engineer", "Vienna Co"),
            make_job("berlin", "Engineer", "Berlin Co"),
            make_job("london", "Engineer", "London Co"),
        ],
    )
    cache.fetch.return_value[0].location = "Vienna, Austria"
    cache.fetch.return_value[1].location = "Berlin, Germany"
    cache.fetch.return_value[2].location = "London, UK"

    jobs, _ = run_search(
        "engineer",
        location="Vienna, Austria",
        preferred_locations=["Vienna, Austria", "Berlin, Germany"],
        cache=cache,
        offline_mode=True,
    )

    assert [job.job_id for job in jobs] == ["vienna", "berlin"]


def test_adzuna_unavailable_without_keys():
    src = AdzunaSource(app_id="", app_key="")
    assert src.available is False
    assert src.fetch("data scientist", None, "us", False, 10) == []


def test_adzuna_does_not_guess_country_for_unknown_location(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Unknown location must not trigger a guessed-country request")

    monkeypatch.setattr(httpx, "get", fail_if_called)
    src = AdzunaSource(app_id="id", app_key="key")
    assert src.fetch("data scientist", "Atlantis", None, False, 10) == []


def test_falls_back_to_cache_when_live_sources_empty():
    adzuna = _fake_source("adzuna", [])
    remotive = _fake_source("remotive", [])
    cache = _fake_source("cache", [make_job("c1", "Data Scientist", "CacheCorp")])
    jobs, used = run_search("data scientist", adzuna=adzuna, remotive=remotive, cache=cache)
    assert used == ["cache"]
    assert len(jobs) == 1


def test_cache_not_used_when_live_results_sufficient():
    adzuna = _fake_source("adzuna", [make_job(f"a{i}", f"Role {i}", f"Co{i}", "adzuna") for i in range(6)])
    remotive = _fake_source("remotive", [])
    cache = _fake_source("cache", [make_job("c1", "X", "Y")])
    jobs, used = run_search("data scientist", adzuna=adzuna, remotive=remotive, cache=cache)
    assert used == ["adzuna"]
    cache.fetch.assert_not_called()


def test_remotive_queried_when_adzuna_thin():
    adzuna = _fake_source("adzuna", [make_job("a1", "One", "Co", "adzuna")])
    remotive = _fake_source("remotive", [make_job(f"r{i}", f"R{i}", f"Ro{i}", "remotive", True) for i in range(4)])
    cache = _fake_source("cache", [])
    jobs, used = run_search("data scientist", adzuna=adzuna, remotive=remotive, cache=cache)
    assert used == ["adzuna", "remotive"]
    remotive.fetch.assert_called_once()


def test_remotive_queried_when_remote_requested():
    adzuna = _fake_source("adzuna", [make_job(f"a{i}", f"Role {i}", f"Co{i}", "adzuna") for i in range(6)])
    remotive = _fake_source("remotive", [make_job("r1", "Remote DS", "RemoteCo", "remotive", True)])
    cache = _fake_source("cache", [])
    jobs, used = run_search("ds", remote=True, adzuna=adzuna, remotive=remotive, cache=cache)
    assert "remotive" in used


def test_dedupe_by_title_company():
    dup = [make_job("a1", "Data Scientist", "Acme", "adzuna")] * 3
    adzuna = _fake_source("adzuna", dup + [make_job(f"a{i}", f"R{i}", f"C{i}", "adzuna") for i in range(5)])
    jobs, _ = run_search("ds", adzuna=adzuna, remotive=_fake_source("r", []), cache=_fake_source("c", []))
    keys = [(j.title, j.company) for j in jobs]
    assert len(keys) == len(set(keys))


def test_result_cap():
    many = [make_job(f"a{i}", f"Role {i}", f"Co{i}", "adzuna") for i in range(40)]
    adzuna = _fake_source("adzuna", many)
    jobs, _ = run_search("ds", limit=25, adzuna=adzuna, remotive=_fake_source("r", []), cache=_fake_source("c", []))
    assert len(jobs) == 25


def test_jsearch_unavailable_without_key():
    src = JSearchSource(api_key="")
    assert src.available is False
    assert src.fetch("data scientist", "Berlin", "de", False, 10) == []


def test_jsearch_builds_location_query_and_maps_fields(respx_mock):
    payload = {
        "data": {
            "cursor": "next-page-token",
            "jobs": [
                {
                    "job_id": "abc",
                    "job_title": "Data Scientist",
                    "employer_name": "Acme GmbH",
                    "job_location": "Berlin • über Stepstone",
                    "job_city": None,
                    "job_country": None,
                    "job_is_remote": False,
                    "job_description": "python and sql",
                    "job_apply_link": "https://example.com/apply",
                    "job_employment_type": "FULLTIME",
                }
            ],
        }
    }
    route = respx_mock.get("https://api.openwebninja.com/jsearch/search-v2").mock(return_value=httpx.Response(200, json=payload))
    src = JSearchSource(api_key="test-key")
    jobs = src.fetch("data scientist", "Berlin, Germany", "us", False, 10)
    # The profile location overrides an inconsistent model-selected country.
    sent = route.calls.last.request
    assert "in Berlin, Germany" in sent.url.params["query"]
    assert sent.url.params["country"] == "de"
    assert sent.headers["X-API-Key"] == "test-key"
    # fields mapped; publisher attribution stripped from location
    assert jobs[0].title == "Data Scientist"
    assert jobs[0].company == "Acme GmbH"
    assert jobs[0].location == "Berlin"
    assert jobs[0].source == "jsearch"


def test_jsearch_primary_when_available():
    jsearch = MagicMock()
    jsearch.available = True
    jsearch.fetch.return_value = [make_job(f"js{i}", f"Role {i}", f"Co{i}", "jsearch") for i in range(6)]
    adzuna = _fake_source("adzuna", [make_job("a1", "X", "Y", "adzuna")])
    jobs, used = run_search(
        "ds",
        location="Berlin",
        jsearch=jsearch,
        adzuna=adzuna,
        remotive=_fake_source("r", []),
        cache=_fake_source("c", []),
    )
    assert used == ["jsearch"]
    adzuna.fetch.assert_not_called()  # JSearch returned enough; Adzuna skipped


def test_cache_source_keyword_match(tmp_path):
    import json

    data = [
        {
            "job_id": "1",
            "title": "Machine Learning Engineer",
            "company": "A",
            "location": "US",
            "remote": False,
            "description": "pytorch and python",
            "url": "",
            "tags": ["ml"],
            "source": "cache",
        },
        {
            "job_id": "2",
            "title": "Chef",
            "company": "B",
            "location": "US",
            "remote": False,
            "description": "cooking",
            "url": "",
            "tags": [],
            "source": "cache",
        },
    ]
    path = tmp_path / "cache.json"
    path.write_text(json.dumps(data))
    src = CacheSource(path=path)
    jobs = src.fetch("machine learning python", None, None, False, 10)
    assert jobs[0].title == "Machine Learning Engineer"
    assert jobs[0].source == "cache"
