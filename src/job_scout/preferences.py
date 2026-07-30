"""Human-confirmed search preferences stored separately from extracted profiles."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from job_scout.config import get_settings
from job_scout.graph.schemas import Profile

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACE = re.compile(r"\s+")
_URL = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)


class SearchPreferenceError(ValueError):
    """Raised for invalid or unreadable local search preferences."""


class SearchPreferences(BaseModel):
    """Explicit locations and remote choice applied only to a search run."""

    model_config = ConfigDict(extra="forbid")

    locations: list[str] = Field(default_factory=list, max_length=10)
    remote: bool = False

    @field_validator("locations")
    @classmethod
    def _normalize_locations(cls, values: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for raw in values:
            value = _SPACE.sub(" ", _CONTROL.sub("", raw)).strip(" ,;")
            if not value:
                continue
            if len(value) > 100:
                raise ValueError("each search location must contain at most 100 characters")
            if _URL.search(value):
                raise ValueError("search locations must not contain URLs")
            key = value.casefold()
            if key not in seen:
                normalized.append(value)
                seen.add(key)
        return normalized

    @model_validator(mode="after")
    def _require_search_scope(self) -> SearchPreferences:
        if not self.locations and not self.remote:
            raise ValueError("select at least one location or enable remote search")
        return self


@dataclass(frozen=True)
class StoredSearchPreferences:
    """One persisted preference record without extracted profile values."""

    profile_key: str
    preferences: SearchPreferences
    updated_at: str


def profile_preference_key(profile: Profile) -> str:
    """Return a stable pseudonymous digest without storing plain profile fields."""
    identity = {
        "name": _SPACE.sub(" ", (profile.name or "").casefold()).strip(),
        "seniority": profile.seniority,
        "primary_roles": sorted(
            _SPACE.sub(" ", value.casefold()).strip()
            for value in profile.primary_roles
        ),
        "skills": sorted(
            _SPACE.sub(" ", value.casefold()).strip()
            for value in profile.skills
        ),
        "years_experience": profile.years_experience,
        "languages": sorted(
            _SPACE.sub(" ", value.casefold()).strip()
            for value in profile.languages
        ),
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def apply_search_preferences(
    profile: Profile,
    preferences: SearchPreferences,
) -> Profile:
    """Return an effective search profile without mutating extracted data."""
    return profile.model_copy(
        update={
            "locations": list(preferences.locations),
            "remote_ok": preferences.remote,
        }
    )


class SearchPreferenceStore:
    """Thread-safe SQLite persistence keyed by a pseudonymous profile digest."""

    def __init__(self, path: str | Path) -> None:
        self.path = path
        if path != ":memory:":
            db_path = Path(path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.path = db_path
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS search_preferences (
                    profile_key TEXT PRIMARY KEY,
                    locations_json TEXT NOT NULL,
                    remote INTEGER NOT NULL CHECK (remote IN (0, 1)),
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(
        self,
        profile: Profile,
        preferences: SearchPreferences,
    ) -> StoredSearchPreferences:
        """Insert or replace one explicitly confirmed preference."""
        profile_key = profile_preference_key(profile)
        updated_at = datetime.now(UTC).isoformat()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO search_preferences (
                    profile_key, locations_json, remote, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_key) DO UPDATE SET
                    locations_json = excluded.locations_json,
                    remote = excluded.remote,
                    updated_at = excluded.updated_at
                """,
                (
                    profile_key,
                    json.dumps(preferences.locations, ensure_ascii=False),
                    int(preferences.remote),
                    updated_at,
                ),
            )
        return StoredSearchPreferences(
            profile_key=profile_key,
            preferences=preferences,
            updated_at=updated_at,
        )

    def get(self, profile: Profile) -> StoredSearchPreferences | None:
        """Load preferences for the same extracted-profile identity."""
        profile_key = profile_preference_key(profile)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT profile_key, locations_json, remote, updated_at
                FROM search_preferences
                WHERE profile_key = ?
                """,
                (profile_key,),
            ).fetchone()
        if row is None:
            return None
        try:
            preferences = SearchPreferences(
                locations=json.loads(row["locations_json"]),
                remote=bool(row["remote"]),
            )
        except Exception as exc:
            raise SearchPreferenceError(
                "Saved search preferences are invalid."
            ) from exc
        return StoredSearchPreferences(
            profile_key=row["profile_key"],
            preferences=preferences,
            updated_at=row["updated_at"],
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()


@lru_cache(maxsize=1)
def get_search_preference_store() -> SearchPreferenceStore:
    """Return the process-wide preference store in the local tracker database."""
    return SearchPreferenceStore(get_settings().application_db_path)
