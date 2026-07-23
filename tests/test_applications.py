"""Tests for the local SQLite application tracker."""

from __future__ import annotations

import pytest

from job_scout.applications import (
    APPLICATION_STATUSES,
    ApplicationStore,
    ApplicationStoreError,
)
from job_scout.graph.schemas import JobPosting, RankedJob


def _ranked(job_id: str = "job-1", score: int = 82) -> RankedJob:
    return RankedJob(
        job=JobPosting(
            job_id=job_id,
            title="ML Engineer",
            company="Example GmbH",
            location="Vienna",
            remote=True,
            description="Python and machine learning",
            url="https://example.com/jobs/1",
            source="cache",
        ),
        fit_score=score,
        fit_explanation="Strong skill match.",
        matched_skills=["python"],
        gaps=["kubernetes"],
    )


@pytest.fixture
def store():
    tracker = ApplicationStore(":memory:")
    yield tracker
    tracker.close()


def test_save_and_list_application(store: ApplicationStore):
    saved = store.save(_ranked(), status="Interested", notes="Contact recruiter")

    assert saved.status == "Interested"
    assert saved.notes == "Contact recruiter"
    assert saved.fit_score == 82
    assert store.list() == [saved]


def test_save_upserts_snapshot_and_preserves_created_at(store: ApplicationStore):
    original = store.save(_ranked(score=70))
    updated = store.save(_ranked(score=91), status="Applied", notes="Applied today")

    assert updated.created_at == original.created_at
    assert updated.fit_score == 91
    assert updated.status == "Applied"
    assert len(store.list()) == 1


def test_update_status_and_notes(store: ApplicationStore):
    store.save(_ranked())

    updated = store.update("job-1", status="Interview", notes="Second round")

    assert updated.status == "Interview"
    assert updated.notes == "Second round"


@pytest.mark.parametrize("status", APPLICATION_STATUSES)
def test_all_documented_statuses_are_supported(store: ApplicationStore, status: str):
    assert store.save(_ranked(), status=status).status == status


def test_invalid_status_and_missing_record_are_rejected(store: ApplicationStore):
    with pytest.raises(ApplicationStoreError, match="Unsupported"):
        store.save(_ranked(), status="Unknown")
    with pytest.raises(ApplicationStoreError, match="no longer exists"):
        store.update("missing", status="Applied")


def test_notes_are_trimmed_and_limited(store: ApplicationStore):
    saved = store.save(_ranked(), notes=f"  {'x' * 2100}  ")

    assert len(saved.notes) == 2000
    assert saved.notes == "x" * 2000


def test_delete_is_explicit_and_scoped(store: ApplicationStore):
    store.save(_ranked("job-1"))
    store.save(_ranked("job-2"))

    assert store.delete("job-1") is True
    assert store.delete("job-1") is False
    assert [record.job_id for record in store.list()] == ["job-2"]


def test_schema_does_not_store_resume_or_secret_fields(store: ApplicationStore):
    store.save(_ranked())

    columns = {
        row[1]
        for row in store._connection.execute("PRAGMA table_info(applications)").fetchall()  # noqa: SLF001
    }

    assert "resume" not in columns
    assert "cv_text" not in columns
    assert "api_key" not in columns
