"""Human-confirmed search preferences and local persistence."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from job_scout.preferences import (
    SearchPreferences,
    SearchPreferenceStore,
    apply_search_preferences,
    profile_preference_key,
)


def test_preferences_normalize_and_deduplicate_locations():
    preferences = SearchPreferences(
        locations=[" Vienna, Austria ", "vienna, austria", "Berlin  Germany"],
        remote=True,
    )

    assert preferences.locations == ["Vienna, Austria", "Berlin Germany"]
    assert preferences.remote is True


@pytest.mark.parametrize(
    "data",
    [
        {"locations": [], "remote": False},
        {"locations": ["https://example.com"], "remote": False},
        {"locations": ["x" * 101], "remote": False},
        {"locations": [f"City {index}" for index in range(11)], "remote": False},
    ],
)
def test_invalid_search_scopes_are_rejected(data):
    with pytest.raises(ValidationError):
        SearchPreferences.model_validate(data)


def test_effective_profile_does_not_mutate_extracted_profile(sample_profile):
    original = sample_profile.model_copy(deep=True)
    preferences = SearchPreferences(
        locations=["Vienna, Austria"],
        remote=False,
    )

    effective = apply_search_preferences(sample_profile, preferences)

    assert effective.locations == ["Vienna, Austria"]
    assert effective.remote_ok is False
    assert sample_profile == original
    assert sample_profile.locations == ["Berlin, Germany"]
    assert sample_profile.remote_ok is True


def test_profile_key_is_stable_but_ignores_extracted_search_guesses(sample_profile):
    changed_search_fields = sample_profile.model_copy(
        update={"locations": ["Atlantis"], "remote_ok": False}
    )

    assert profile_preference_key(sample_profile) == profile_preference_key(
        changed_search_fields
    )
    assert len(profile_preference_key(sample_profile)) == 64


def test_profile_key_changes_for_another_candidate_identity(sample_profile):
    other = sample_profile.model_copy(update={"name": "Another Candidate"})

    assert profile_preference_key(sample_profile) != profile_preference_key(other)


def test_store_round_trip_and_update(tmp_path, sample_profile):
    store = SearchPreferenceStore(tmp_path / "preferences.db")
    first = SearchPreferences(locations=["Vienna"], remote=False)
    second = SearchPreferences(locations=["Berlin"], remote=True)

    try:
        saved = store.save(sample_profile, first)
        assert store.get(sample_profile) == saved

        updated = store.save(sample_profile, second)
        loaded = store.get(sample_profile)
        assert loaded == updated
        assert loaded is not None
        assert loaded.preferences == second
    finally:
        store.close()


def test_store_schema_contains_no_profile_or_contact_fields(
    tmp_path,
    sample_profile,
):
    store = SearchPreferenceStore(tmp_path / "preferences.db")
    store.save(
        sample_profile,
        SearchPreferences(locations=["Vienna"], remote=True),
    )

    try:
        columns = {
            row[1]
            for row in store._connection.execute(  # noqa: SLF001
                "PRAGMA table_info(search_preferences)"
            ).fetchall()
        }
        values = store._connection.execute(  # noqa: SLF001
            "SELECT * FROM search_preferences"
        ).fetchone()
        serialized = " ".join(str(value) for value in values)
    finally:
        store.close()

    assert columns == {
        "profile_key",
        "locations_json",
        "remote",
        "updated_at",
    }
    assert "Test Candidate" not in serialized
    assert "Berlin, Germany" not in serialized
