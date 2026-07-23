"""Local SQLite persistence for the application tracker."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import RLock

from job_scout.config import get_settings
from job_scout.graph.schemas import RankedJob

APPLICATION_STATUSES = (
    "Found",
    "Interested",
    "Applied",
    "Interview",
    "Rejected",
    "Offer",
)


class ApplicationStoreError(ValueError):
    """Raised for an invalid tracker operation."""


@dataclass(frozen=True)
class ApplicationRecord:
    """One locally saved job and its user-managed application state."""

    job_id: str
    title: str
    company: str
    location: str
    url: str
    source: str
    fit_score: int
    status: str
    notes: str
    created_at: str
    updated_at: str


class ApplicationStore:
    """Thread-safe SQLite store with one connection per application process."""

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
                CREATE TABLE IF NOT EXISTS applications (
                    job_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT NOT NULL,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL,
                    fit_score INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _validate_status(status: str) -> str:
        normalized = status.strip()
        if normalized not in APPLICATION_STATUSES:
            raise ApplicationStoreError(f"Unsupported application status: {status}")
        return normalized

    @staticmethod
    def _notes(value: str) -> str:
        return value.strip()[:2000]

    def save(self, ranked: RankedJob, status: str = "Found", notes: str = "") -> ApplicationRecord:
        """Insert a ranked job or update its mutable tracker fields."""
        normalized_status = self._validate_status(status)
        now = datetime.now(UTC).isoformat()
        job = ranked.job
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO applications (
                    job_id, title, company, location, url, source, fit_score,
                    status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    url = excluded.url,
                    source = excluded.source,
                    fit_score = excluded.fit_score,
                    status = excluded.status,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    job.job_id,
                    job.title,
                    job.company,
                    job.location,
                    job.url,
                    job.source,
                    ranked.fit_score,
                    normalized_status,
                    self._notes(notes),
                    now,
                    now,
                ),
            )
        record = self.get(job.job_id)
        if record is None:
            raise ApplicationStoreError("The application could not be saved.")
        return record

    def update(self, job_id: str, status: str, notes: str = "") -> ApplicationRecord:
        """Update status and notes for an existing application."""
        normalized_status = self._validate_status(status)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE applications
                SET status = ?, notes = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (normalized_status, self._notes(notes), datetime.now(UTC).isoformat(), job_id),
            )
        if cursor.rowcount != 1:
            raise ApplicationStoreError("The selected application no longer exists.")
        record = self.get(job_id)
        if record is None:
            raise ApplicationStoreError("The application could not be loaded after updating.")
        return record

    def delete(self, job_id: str) -> bool:
        """Delete one explicitly selected application."""
        with self._lock, self._connection:
            cursor = self._connection.execute("DELETE FROM applications WHERE job_id = ?", (job_id,))
        return cursor.rowcount == 1

    def get(self, job_id: str) -> ApplicationRecord | None:
        """Return one application by job identifier."""
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM applications WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return ApplicationRecord(**dict(row)) if row else None

    def list(self) -> list[ApplicationRecord]:
        """Return newest-updated applications first."""
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM applications ORDER BY updated_at DESC, job_id ASC"
            ).fetchall()
        return [ApplicationRecord(**dict(row)) for row in rows]

    def close(self) -> None:
        """Close the connection, primarily for isolated tests."""
        with self._lock:
            self._connection.close()


@lru_cache(maxsize=1)
def get_application_store() -> ApplicationStore:
    """Return the process-wide local application store."""
    return ApplicationStore(get_settings().application_db_path)
