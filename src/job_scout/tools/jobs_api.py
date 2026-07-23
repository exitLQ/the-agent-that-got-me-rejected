"""Job search exposed to the agent as a single ``search_jobs`` tool.

Behind the tool, ``run_search`` uses the committed cache in offline mode. In
online mode it fans out to pluggable ``JobSource`` adapters:

    JSearch → Adzuna → Remotive → committed cache

Each adapter is tried only if the ones before it returned too few eligible jobs.
All results pass through the same deterministic location filter. No scraping
sources are included (see ``docs/extending_sources.md``).
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx
from langchain_core.tools import tool

from job_scout.config import get_settings
from job_scout.graph.schemas import JobPosting

DESCRIPTION_LIMIT = 4000
DEFAULT_LIMIT = 25
CACHE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cached_jobs.json"

_COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "at": ("austria", "osterreich"),
    "au": ("australia",),
    "br": ("brazil", "brasil"),
    "ca": ("canada",),
    "ch": ("switzerland", "schweiz", "suisse"),
    "de": ("germany", "deutschland"),
    "es": ("spain", "espana"),
    "fr": ("france",),
    "gb": ("united kingdom", "great britain", "england", "scotland", "wales", "uk"),
    "in": ("india",),
    "it": ("italy", "italia"),
    "mx": ("mexico",),
    "nl": ("netherlands", "nederland"),
    "pl": ("poland", "polska"),
    "sg": ("singapore",),
    "uy": ("uruguay",),
    "us": ("united states", "united states of america", "usa"),
}
_CITY_COUNTRIES: dict[str, str] = {
    "bangalore": "in",
    "bengaluru": "in",
    "berlin": "de",
    "brisbane": "au",
    "chennai": "in",
    "delhi": "in",
    "dusseldorf": "de",
    "essen": "de",
    "frankfurt": "de",
    "hamburg": "de",
    "hyderabad": "in",
    "london": "gb",
    "melbourne": "au",
    "mumbai": "in",
    "munich": "de",
    "munchen": "de",
    "new york": "us",
    "pune": "in",
    "san francisco": "us",
    "sao paulo": "br",
    "sydney": "au",
    "toronto": "ca",
    "vienna": "at",
    "wien": "at",
    "zurich": "ch",
}
_REGION_COUNTRIES: dict[str, str] = {
    "allegheny county": "us",
    "berkshire": "gb",
    "bayern": "de",
    "central london": "gb",
    "county down": "gb",
    "county tyrone": "gb",
    "dachau kreis": "de",
    "fairfax county": "us",
    "fulton county": "us",
    "ghaziabad": "in",
    "gloucestershire": "gb",
    "hertfordshire": "gb",
    "karnataka": "in",
    "kreis": "de",
    "madhya pradesh": "in",
    "maharashtra": "in",
    "melbourne region": "au",
    "nordrhein westfalen": "de",
    "northern ireland": "gb",
    "schleswig holstein": "de",
    "south canberra": "au",
    "south west england": "gb",
    "sydney region": "au",
    "tamil nadu": "in",
    "telangana": "in",
    "upper austria": "at",
    "uttar pradesh": "in",
    "warwickshire": "gb",
    "west midlands": "gb",
}
_EUROPE_COUNTRIES = {"at", "ch", "de", "es", "fr", "gb", "it", "nl", "pl"}
_AMERICAS_COUNTRIES = {"br", "ca", "mx", "us", "uy"}
_LATAM_COUNTRIES = {"br", "mx", "uy"}
_APAC_COUNTRIES = {"au", "in", "sg"}
_GLOBAL_LOCATIONS = {"anywhere", "global", "remote", "worldwide", "world"}
_CITY_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "bangalore": ("bangalore", "bengaluru"),
    "cologne": ("cologne", "koln"),
    "munich": ("munich", "munchen"),
    "sao paulo": ("sao paulo",),
    "vienna": ("vienna", "wien"),
    "zurich": ("zurich",),
}


def normalize_location(value: str | None) -> str:
    """Return a case- and accent-insensitive location string."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text).split())


def _contains_location_phrase(location: str, phrase: str) -> bool:
    """Match a normalized location phrase on word boundaries."""
    return bool(re.search(rf"(?:^| ){re.escape(phrase)}(?: |$)", location))


def location_to_country(location: str | None) -> str | None:
    """Map free-text location to a country code without guessing a default."""
    if not location:
        return None
    loc = normalize_location(location)
    if len(loc) == 2 and loc in _COUNTRY_ALIASES:
        return loc
    for code, aliases in _COUNTRY_ALIASES.items():
        if any(_contains_location_phrase(loc, alias) for alias in aliases):
            return code
    for city, code in _CITY_COUNTRIES.items():
        if _contains_location_phrase(loc, city):
            return code
    for region, code in _REGION_COUNTRIES.items():
        if _contains_location_phrase(loc, region):
            return code
    return None


def normalize_country_code(country: str | None) -> str | None:
    """Validate a country code or resolve a country name to its code."""
    normalized = normalize_location(country)
    if len(normalized) == 2 and normalized in _COUNTRY_ALIASES:
        return normalized
    return location_to_country(country)


def _canonical_city(location: str) -> str:
    """Resolve known translated city names to one stable identifier."""
    for canonical, aliases in _CITY_EQUIVALENTS.items():
        if any(_contains_location_phrase(location, alias) for alias in aliases):
            return canonical
    for city in _CITY_COUNTRIES:
        if _contains_location_phrase(location, city):
            return city
    return ""


def _remote_scope_matches(offered: str, wanted_country: str) -> bool:
    """Whether a remote posting's stated geographical scope includes a country."""
    tokens = set(offered.split())
    if tokens & _GLOBAL_LOCATIONS:
        return True
    return (
        ("europe" in tokens and wanted_country in _EUROPE_COUNTRIES)
        or (("america" in tokens or "americas" in tokens) and wanted_country in _AMERICAS_COUNTRIES)
        or ("latam" in tokens and wanted_country in _LATAM_COUNTRIES)
        or (("apac" in tokens or "asia" in tokens or "oceania" in tokens) and wanted_country in _APAC_COUNTRIES)
    )


def _mentions_country(location: str, country: str) -> bool:
    """Whether a normalized location explicitly includes one country."""
    if not country:
        return False
    if country in location.split():
        return True
    if any(_contains_location_phrase(location, alias) for alias in _COUNTRY_ALIASES.get(country, ())):
        return True
    return any(
        code == country and _contains_location_phrase(location, city)
        for city, code in _CITY_COUNTRIES.items()
    )


def location_match_rank(
    job_location: str,
    requested_location: str | None,
    requested_country: str | None,
    *,
    job_remote: bool,
    remote_requested: bool,
) -> int:
    """Return a deterministic location rank, or zero for a known mismatch.

    Rank 4 is an exact city/locality match, 3 is an eligible remote match,
    2 is a same-country fallback, and 1 means no location preference was given.
    """
    wanted = normalize_location(requested_location)
    offered = normalize_location(job_location)
    country = normalize_country_code(requested_country) or ""

    if not wanted and not country:
        return 3 if job_remote and remote_requested else 1

    wanted_country = country or location_to_country(requested_location) or ""
    offered_country = location_to_country(job_location) or ""
    wanted_locality = _canonical_city(wanted)
    offered_locality = _canonical_city(offered)
    if not wanted_locality and wanted:
        is_country_only = wanted_country and any(
            wanted == alias for alias in _COUNTRY_ALIASES.get(wanted_country, ())
        )
        if not is_country_only:
            wanted_locality = normalize_location((requested_location or "").split(",", maxsplit=1)[0])

    if wanted_locality and (
        wanted_locality == offered_locality
        or (offered and _contains_location_phrase(offered, wanted_locality))
    ):
        return 4

    if job_remote and remote_requested:
        if _remote_scope_matches(offered, wanted_country):
            return 3
        if _mentions_country(offered, wanted_country) or (
            wanted_country and offered_country == wanted_country
        ):
            return 3
        return 0

    if wanted_country and offered_country == wanted_country:
        return 2
    return 0


def _rank_location_matches(
    jobs: list[JobPosting],
    locations: list[str],
    country: str | None,
    remote: bool,
) -> list[JobPosting]:
    """Filter known location mismatches and order exact matches first."""
    ranked: list[tuple[int, JobPosting]] = []
    for job in jobs:
        ranks = [
            location_match_rank(
                job.location,
                location,
                None,
                job_remote=job.remote,
                remote_requested=remote,
            )
            for location in locations
        ]
        if not ranks:
            ranks = [
                location_match_rank(
                    job.location,
                    None,
                    country,
                    job_remote=job.remote,
                    remote_requested=remote,
                )
            ]
        ranked.append((max(ranks), job))
    return [job for rank, job in sorted(ranked, key=lambda item: item[0], reverse=True) if rank > 0]


def _truncate(text: str) -> str:
    """Cap a description at ``DESCRIPTION_LIMIT`` characters."""
    return (text or "")[:DESCRIPTION_LIMIT]


class JobSource(Protocol):
    """A pluggable jobs backend.

    Adapters must never raise on a network or parse error; they return an empty
    list so ``run_search`` can fall through to the next source.
    """

    name: str

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        """Return postings matching the query, or an empty list on any failure."""
        ...


class JSearchSource:
    """Official Google-for-Jobs aggregator (OpenWeb Ninja) with city-level search.

    Location is honoured deterministically: the location is folded into the query
    (``"<query> in <location>"``) and the country code is derived from it, so a
    Berlin CV returns Berlin jobs regardless of how the query was phrased.
    """

    name = "jsearch"
    BASE = "https://api.openwebninja.com/jsearch/search-v2"

    def __init__(self, api_key: str = "", timeout: float = 15.0) -> None:
        self.api_key = api_key or get_settings().jsearch_api_key.get_secret_value()
        self.timeout = timeout

    @property
    def available(self) -> bool:
        """Whether an API key is configured."""
        return bool(self.api_key)

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        """Fetch one page (10 results = 1 request credit; the free tier is small)."""
        if not self.available:
            return []
        params: dict[str, object] = {
            "query": f"{query} in {location}" if location else query,
            "num_pages": 1,
        }
        resolved_country = location_to_country(location) or normalize_country_code(country)
        if resolved_country:
            params["country"] = resolved_country
        if remote:
            params["work_from_home"] = "true"
        try:
            resp = httpx.get(self.BASE, params=params, headers={"X-API-Key": self.api_key}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            return []
        payload = data.get("data")
        rows = payload.get("jobs") if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        return [self._to_posting(r) for r in (rows or [])[:limit]]

    @staticmethod
    def _clean_location(r: dict) -> str:
        """Extract the location from JSearch, dropping the ``• via <publisher>`` suffix."""
        raw = (r.get("job_location") or "").split("•")[0].strip()
        if raw:
            return raw
        parts = [r.get("job_city"), r.get("job_state"), r.get("job_country")]
        return ", ".join(p for p in parts if p) or "Unspecified"

    @staticmethod
    def _to_posting(r: dict) -> JobPosting:
        """Convert one JSearch result into a ``JobPosting``."""
        return JobPosting(
            job_id=f"jsearch-{r.get('job_id') or r.get('id', '')}",
            title=(r.get("job_title") or "").strip() or "Untitled",
            company=(r.get("employer_name") or "").strip() or "Unknown",
            location=JSearchSource._clean_location(r),
            remote=bool(r.get("job_is_remote")),
            description=_truncate(r.get("job_description") or ""),
            url=r.get("job_apply_link") or "",
            tags=[t for t in [r.get("job_employment_type"), r.get("job_publisher")] if t],
            source="jsearch",
        )


class AdzunaSource:
    """Free official jobs API covering ~20 countries; needs an app id and key."""

    name = "adzuna"
    BASE = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self, app_id: str = "", app_key: str = "", timeout: float = 10.0) -> None:
        settings = get_settings()
        self.app_id = app_id or settings.adzuna_app_id.get_secret_value()
        self.app_key = app_key or settings.adzuna_app_key.get_secret_value()
        self.timeout = timeout

    @property
    def available(self) -> bool:
        """Whether both credentials are configured."""
        return bool(self.app_id and self.app_key)

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        """Fetch postings for one country (derived from ``country`` or the location)."""
        if not self.available:
            return []
        code = location_to_country(location) or normalize_country_code(country)
        if not code:
            return []
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
            resp = httpx.get(f"{self.BASE}/{code}/search/1", params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            return []
        return [self._to_posting(r, code) for r in data.get("results", [])]

    @staticmethod
    def _to_posting(r: dict, code: str) -> JobPosting:
        """Convert one Adzuna result into a ``JobPosting``."""
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


class RemotiveSource:
    """Keyless API of worldwide remote jobs."""

    name = "remotive"
    BASE = "https://remotive.com/api/remote-jobs"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        """Fetch remote postings matching the query."""
        try:
            resp = httpx.get(self.BASE, params={"search": query, "limit": limit}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            return []
        return [self._to_posting(r) for r in data.get("jobs", [])[:limit]]

    @staticmethod
    def _to_posting(r: dict) -> JobPosting:
        """Convert one Remotive result into a ``JobPosting``."""
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


class CacheSource:
    """Offline fallback: keyword search over the committed ``cached_jobs.json``."""

    name = "cache"

    def __init__(self, path: Path = CACHE_PATH) -> None:
        self.path = path

    def _load(self) -> list[dict]:
        """Load the cached postings, or an empty list if the file is missing/invalid."""
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def metadata(self) -> dict[str, str | int]:
        """Return local cache provenance for offline-mode status displays."""
        rows = self._load()
        try:
            modified = datetime.fromtimestamp(self.path.stat().st_mtime, tz=UTC).date().isoformat()
        except OSError:
            modified = "unknown"
        return {
            "path": str(self.path),
            "job_count": len(rows),
            "modified_date": modified,
        }

    def fetch(self, query: str, location: str | None, country: str | None, remote: bool, limit: int) -> list[JobPosting]:
        """Rank cached postings by how many query terms they contain."""
        terms = [t for t in re.split(r"\W+", query.lower()) if t]
        scored: list[tuple[int, dict]] = []
        for row in self._load():
            haystack = f"{row.get('title', '')} {row.get('description', '')} {' '.join(row.get('tags', []))}".lower()
            score = sum(1 for t in terms if t in haystack) + (1 if remote and row.get("remote") else 0)
            if score > 0 or not terms:
                scored.append((score, row))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [
            JobPosting(**{**row, "source": "cache", "description": _truncate(row.get("description", ""))})
            for _, row in scored[:limit]
        ]


def _dedupe(jobs: list[JobPosting]) -> list[JobPosting]:
    """Drop jobs sharing a ``(title, company)`` with an earlier one."""
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
    jsearch: JSearchSource | None = None,
    adzuna: AdzunaSource | None = None,
    remotive: RemotiveSource | None = None,
    cache: CacheSource | None = None,
    offline_mode: bool | None = None,
    preferred_locations: list[str] | None = None,
) -> tuple[list[JobPosting], list[str]]:
    """Search across the sources in order and return ``(jobs, sources_used)``.

    A source is only queried if the previous ones returned too few
    location-eligible jobs. Results are location-filtered, merged, deduped by
    ``(title, company)`` and capped at ``limit``. ``preferred_locations`` allows
    every location in a profile to participate in post-filtering while
    ``location`` remains the primary live-provider query. Sources are injectable
    for testing. ``sources_used`` goes into trace metadata.
    """
    cache = cache or CacheSource()
    raw_locations = preferred_locations if preferred_locations is not None else ([location] if location else [])
    match_locations = [item for item in raw_locations if normalize_location(item)]
    if offline_mode is None:
        offline_mode = get_settings().offline_mode
    if offline_mode:
        cached = _rank_location_matches(
            _dedupe(cache.fetch(query, location, country, remote, limit)),
            match_locations,
            country,
            remote,
        )[:limit]
        return cached, ["cache"] if cached else []

    jsearch = jsearch or JSearchSource()
    adzuna = adzuna or AdzunaSource()
    remotive = remotive or RemotiveSource()

    jobs: list[JobPosting] = []
    used: list[str] = []

    def add(source_name: str, found: list[JobPosting]) -> None:
        """Record a source's results if it returned any."""
        found = _rank_location_matches(found, match_locations, country, remote)
        if found:
            used.append(source_name)
            jobs.extend(found)

    if jsearch.available:
        add("jsearch", jsearch.fetch(query, location, country, remote, limit))
    if len(_dedupe(jobs)) < 5:
        add("adzuna", adzuna.fetch(query, location, country, remote, limit))
    if remote or len(_dedupe(jobs)) < 5:
        add("remotive", remotive.fetch(query, location, country, remote, limit))
    if len(_dedupe(jobs)) < 3:
        add("cache", cache.fetch(query, location, country, remote, limit))

    return _dedupe(jobs)[:limit], used


@tool
def search_jobs(query: str, country: str | None = None, remote: bool = False, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Search for open job postings matching a query.

    Args:
        query: Role/skill search terms, e.g. "machine learning engineer python".
        country: Two-letter country code (us, gb, de, in, au, br, ...). Omit to
            infer it from the query text.
        remote: Set true to prioritise remote-friendly roles.
        limit: Maximum number of postings to return.

    Returns:
        A list of job postings as dicts (title, company, location, description, url).
    """
    jobs, _sources = run_search(query=query, country=country, remote=remote, limit=limit)
    return [job.model_dump() for job in jobs]
