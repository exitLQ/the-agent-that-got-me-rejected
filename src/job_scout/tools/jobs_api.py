"""Jobs search: a single LangChain tool over three pluggable sources.

The agent sees exactly one tool, ``search_jobs``. Internally it fans out to
``JobSource`` adapters, tried in order and merged:

  1. AdzunaSource   - primary; official API, ~20 countries, needs free keys.
  2. RemotiveSource - keyless worldwide remote jobs; queried when the candidate
                      is remote-friendly or Adzuna returned too few results.
  3. CacheSource    - committed offline dataset; the safety net on any network
                      error, missing keys, or when live sources are too thin.

No scraping sources, ever (see docs/extending_sources.md).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

import httpx
from langchain_core.tools import tool

from job_scout.config import get_settings
from job_scout.schemas import JobPosting

DESCRIPTION_LIMIT = 4000
DEFAULT_LIMIT = 25
CACHE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cached_jobs.json"

# Country name / location keyword -> Adzuna country code.
_COUNTRY_CODES: dict[str, str] = {
    "united states": "us",
    "usa": "us",
    "us": "us",
    "america": "us",
    "united kingdom": "gb",
    "uk": "gb",
    "england": "gb",
    "london": "gb",
    "germany": "de",
    "deutschland": "de",
    "berlin": "de",
    "munich": "de",
    "münchen": "de",
    "india": "in",
    "bengaluru": "in",
    "bangalore": "in",
    "mumbai": "in",
    "delhi": "in",
    "australia": "au",
    "sydney": "au",
    "melbourne": "au",
    "brazil": "br",
    "brasil": "br",
    "são paulo": "br",
    "sao paulo": "br",
    "canada": "ca",
    "france": "fr",
    "spain": "es",
    "netherlands": "nl",
    "singapore": "sg",
    "poland": "pl",
    "italy": "it",
}
DEFAULT_COUNTRY = "us"


def location_to_country(location: str | None) -> str:
    """Map a free-text location to an Adzuna country code (default ``us``)."""
    if not location:
        return DEFAULT_COUNTRY
    loc = location.strip().lower()
    for keyword, code in _COUNTRY_CODES.items():
        if keyword in loc:
            return code
    return DEFAULT_COUNTRY


def _truncate(text: str) -> str:
    return (text or "")[:DESCRIPTION_LIMIT]


# --- Source protocol ---------------------------------------------------------


class JobSource(Protocol):
    """A pluggable jobs backend. Adapters must not raise on network errors —
    they return an empty list so the orchestrator can fall through to cache."""

    name: str

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]: ...


# --- Adzuna ------------------------------------------------------------------


class AdzunaSource:
    name = "adzuna"
    BASE = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self, app_id: str = "", app_key: str = "", timeout: float = 10.0) -> None:
        settings = get_settings()
        self.app_id = app_id or settings.adzuna_app_id.get_secret_value()
        self.app_key = app_key or settings.adzuna_app_key.get_secret_value()
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.app_id and self.app_key)

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        if not self.available:
            return []
        code = country or location_to_country(location)
        url = f"{self.BASE}/{code}/search/1"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": min(limit, 50),
            "what": query,
            "content-type": "application/json",
        }
        if location:
            params["where"] = location
        try:
            resp = httpx.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            return []
        return [self._to_posting(r, code) for r in data.get("results", [])]

    @staticmethod
    def _to_posting(r: dict, code: str) -> JobPosting:
        loc = (r.get("location") or {}).get("display_name") or code.upper()
        return JobPosting(
            job_id=f"adzuna-{r.get('id', '')}",
            title=r.get("title", "").strip() or "Untitled",
            company=(r.get("company") or {}).get("display_name", "").strip() or "Unknown",
            location=loc,
            remote="remote" in (r.get("title", "") + loc).lower(),
            description=_truncate(r.get("description", "")),
            url=r.get("redirect_url", ""),
            tags=[c.get("label", "") for c in [r.get("category", {})] if c.get("label")],
            source="adzuna",
        )


# --- Remotive ----------------------------------------------------------------


class RemotiveSource:
    name = "remotive"
    BASE = "https://remotive.com/api/remote-jobs"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        try:
            resp = httpx.get(self.BASE, params={"search": query, "limit": limit}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            return []
        return [self._to_posting(r) for r in data.get("jobs", [])[:limit]]

    @staticmethod
    def _to_posting(r: dict) -> JobPosting:
        return JobPosting(
            job_id=f"remotive-{r.get('id', '')}",
            title=r.get("title", "").strip() or "Untitled",
            company=r.get("company_name", "").strip() or "Unknown",
            location=r.get("candidate_required_location") or "Remote",
            remote=True,
            description=_truncate(r.get("description", "")),
            url=r.get("url", ""),
            tags=r.get("tags", []) or [],
            source="remotive",
        )


# --- Cache -------------------------------------------------------------------


class CacheSource:
    name = "cache"

    def __init__(self, path: Path = CACHE_PATH) -> None:
        self.path = path

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        rows = self._load()
        terms = [t for t in re.split(r"\W+", query.lower()) if t]
        scored: list[tuple[int, dict]] = []
        for row in rows:
            haystack = f"{row.get('title', '')} {row.get('description', '')} {' '.join(row.get('tags', []))}".lower()
            score = sum(1 for t in terms if t in haystack)
            if remote and row.get("remote"):
                score += 1
            if score > 0 or not terms:
                scored.append((score, row))
        scored.sort(key=lambda s: s[0], reverse=True)
        out = []
        for _, row in scored[:limit]:
            row = {**row, "source": "cache", "description": _truncate(row.get("description", ""))}
            out.append(JobPosting(**row))
        return out


# --- Orchestration -----------------------------------------------------------


def _dedupe(jobs: list[JobPosting]) -> list[JobPosting]:
    seen: set[tuple[str, str]] = set()
    out: list[JobPosting] = []
    for job in jobs:
        key = (job.title.strip().lower(), job.company.strip().lower())
        if key not in seen:
            seen.add(key)
            out.append(job)
    return out


def run_search(
    query: str,
    location: str | None = None,
    country: str | None = None,
    remote: bool = False,
    limit: int = DEFAULT_LIMIT,
    *,
    adzuna: AdzunaSource | None = None,
    remotive: RemotiveSource | None = None,
    cache: CacheSource | None = None,
) -> tuple[list[JobPosting], list[str]]:
    """Run the search across sources and return ``(jobs, sources_used)``.

    Order: Adzuna (primary) → Remotive (when remote-friendly or Adzuna thin) →
    Cache (when the combined live result is still < 3, or nothing else ran).
    Results are merged, deduped by ``(title, company)`` and capped at ``limit``.
    The ``sources_used`` list is recorded into trace metadata.
    """
    adzuna = adzuna or AdzunaSource()
    remotive = remotive or RemotiveSource()
    cache = cache or CacheSource()

    jobs: list[JobPosting] = []
    used: list[str] = []

    adzuna_jobs = adzuna.fetch(query, location, country, remote, limit)
    if adzuna_jobs:
        used.append("adzuna")
        jobs.extend(adzuna_jobs)

    if remote or len(adzuna_jobs) < 5:
        remotive_jobs = remotive.fetch(query, location, country, remote, limit)
        if remotive_jobs:
            used.append("remotive")
            jobs.extend(remotive_jobs)

    if len(_dedupe(jobs)) < 3:
        cache_jobs = cache.fetch(query, location, country, remote, limit)
        if cache_jobs:
            used.append("cache")
            jobs.extend(cache_jobs)

    return _dedupe(jobs)[:limit], used


# --- The single tool the agent sees ------------------------------------------


@tool
def search_jobs(query: str, country: str | None = None, remote: bool = False, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Search for open job postings matching a query.

    Args:
        query: Role/skill search terms, e.g. "machine learning engineer python".
        country: Two-letter country code (us, gb, de, in, au, br, ...). Omit to
            infer from the query text.
        remote: Set true to prioritise remote-friendly roles.
        limit: Maximum number of postings to return (default 25).

    Returns a list of job postings (title, company, location, description, url).
    """
    jobs, _used = run_search(query=query, country=country, remote=remote, limit=limit)
    return [j.model_dump() for j in jobs]
