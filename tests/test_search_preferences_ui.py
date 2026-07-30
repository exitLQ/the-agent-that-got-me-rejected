"""Human confirmation and effective-profile isolation in the Gradio flow."""

from __future__ import annotations

from types import SimpleNamespace

import job_scout.app as app
from job_scout.preferences import SearchPreferences
from job_scout.runner import RunResult


class FakeStore:
    def __init__(self, stored=None, *, fail_save: bool = False):
        self.stored = stored
        self.fail_save = fail_save
        self.saved = []

    def get(self, profile):
        return self.stored

    def save(self, profile, preferences):
        if self.fail_save:
            raise OSError("private storage failure")
        self.saved.append((profile, preferences))


def test_saved_preferences_are_loaded_but_require_fresh_confirmation(
    monkeypatch,
    sample_profile,
):
    stored_preferences = SearchPreferences(
        locations=["Vienna, Austria"],
        remote=False,
    )
    store = FakeStore(
        SimpleNamespace(preferences=stored_preferences),
    )
    monkeypatch.setattr(app, "get_search_preference_store", lambda: store)

    locations, remote, confirmed, status = app._preference_controls(sample_profile)

    assert locations["choices"] == ["Berlin, Germany", "Vienna, Austria"]
    assert locations["value"] == ["Vienna, Austria"]
    assert remote is False
    assert confirmed is False
    assert "Saved search preferences loaded" in status


def test_search_is_blocked_before_store_or_runner_without_confirmation(
    monkeypatch,
    sample_profile,
):
    monkeypatch.setattr(
        app,
        "get_search_preference_store",
        lambda: (_ for _ in ()).throw(AssertionError("store accessed")),
    )
    monkeypatch.setattr(
        app,
        "stream_search",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("search started")
        ),
    )

    events = list(
        app.on_find(
            sample_profile,
            "thread-1",
            "ollama:qwen3:8b",
            ["Vienna, Austria"],
            True,
            False,
        )
    )

    assert len(events) == 1
    assert events[0][0]["visible"] is True
    assert events[0][1]["visible"] is False
    assert "Review and confirm" in events[0][8]


def test_invalid_confirmed_scope_is_blocked_before_store_or_runner(
    monkeypatch,
    sample_profile,
):
    monkeypatch.setattr(
        app,
        "get_search_preference_store",
        lambda: (_ for _ in ()).throw(AssertionError("store accessed")),
    )
    monkeypatch.setattr(
        app,
        "stream_search",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("search started")
        ),
    )

    event = list(
        app.on_find(
            sample_profile,
            "thread-1",
            "ollama:qwen3:8b",
            [],
            False,
            True,
        )
    )[0]

    assert "Select at least one valid location" in event[8]


def test_confirmed_preferences_create_effective_profile_without_mutation(
    monkeypatch,
    sample_profile,
):
    original = sample_profile.model_copy(deep=True)
    captured = {}
    store = FakeStore()
    monkeypatch.setattr(app, "get_search_preference_store", lambda: store)

    def fake_stream(profile, **kwargs):
        captured["profile"] = profile
        captured["kwargs"] = kwargs
        yield "result", RunResult(profile=profile, model=kwargs["model_name"])

    monkeypatch.setattr(app, "stream_search", fake_stream)

    final = list(
        app.on_find(
            sample_profile,
            "thread-1",
            "ollama:qwen3:8b",
            ["Vienna, Austria"],
            False,
            True,
        )
    )[-1]

    effective = captured["profile"]
    assert effective.locations == ["Vienna, Austria"]
    assert effective.remote_ok is False
    assert sample_profile == original
    assert store.saved == [
        (
            sample_profile,
            SearchPreferences(locations=["Vienna, Austria"], remote=False),
        )
    ]
    assert "human-confirmed search scope" in final[3]
    assert "locations: Vienna, Austria" in final[3]
    assert "remote: excluded" in final[3]
    assert captured["kwargs"] == {
        "thread_id": "thread-1",
        "tags": ["phase-1", "ui"],
        "model_name": "ollama:qwen3:8b",
    }


def test_persistence_failure_does_not_discard_confirmed_scope(
    monkeypatch,
    sample_profile,
):
    captured = {}
    monkeypatch.setattr(
        app,
        "get_search_preference_store",
        lambda: FakeStore(fail_save=True),
    )

    def fake_stream(profile, **kwargs):
        captured["profile"] = profile
        yield "result", RunResult(profile=profile, model=kwargs["model_name"])

    monkeypatch.setattr(app, "stream_search", fake_stream)

    final = list(
        app.on_find(
            sample_profile,
            "thread-1",
            "ollama:qwen3:8b",
            ["Vienna"],
            True,
            True,
        )
    )[-1]

    assert captured["profile"].locations == ["Vienna"]
    assert captured["profile"].remote_ok is True
    assert "could not be saved locally" in final[8]


def test_editing_preferences_invalidates_confirmation():
    assert app.on_preferences_change() == (False, "")
