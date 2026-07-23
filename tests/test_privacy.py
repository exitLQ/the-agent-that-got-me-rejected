"""Privacy-mode guarantees for settings, graph inputs, prompts, and uploads."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import job_scout.runner as runner_mod
import job_scout.tracing as tracing_mod
from job_scout.config import Settings
from job_scout.graph.nodes.rank_jobs import _render_profile
from job_scout.privacy import delete_temporary_upload
from job_scout.runner import stream_search


class _CapturingGraph:
    def __init__(self):
        self.inputs = None

    def stream(self, inputs, config, stream_mode):
        self.inputs = inputs
        return iter(())

    def get_state(self, config):
        return SimpleNamespace(values={"profile": None})


def test_privacy_mode_is_enabled_by_default_and_disables_opik(monkeypatch):
    monkeypatch.delenv("PRIVACY_MODE", raising=False)
    settings = Settings(
        _env_file=None,
        OFFLINE_MODE=False,
        OPIK_ENABLED=True,
        OPIK_API_KEY="configured",
    )

    assert settings.privacy_mode is True
    assert settings.has_opik is False


def test_graph_input_never_contains_raw_cv_text(monkeypatch, sample_profile):
    graph = _CapturingGraph()
    monkeypatch.setattr(runner_mod, "build_graph", lambda: graph)
    monkeypatch.setattr(runner_mod, "trace_graph", lambda compiled, tracer: compiled)
    monkeypatch.setattr(runner_mod, "get_tracer", lambda *args, **kwargs: None)

    list(stream_search(sample_profile, cv_text="private resume text", thread_id="privacy", tags=["test"]))

    assert graph.inputs["profile"] is sample_profile
    assert "cv_text" not in graph.inputs


def test_privacy_mode_blocks_cv_attachment_at_runner_boundary(monkeypatch, sample_profile):
    graph = _CapturingGraph()
    monkeypatch.setattr(runner_mod, "build_graph", lambda: graph)
    monkeypatch.setattr(runner_mod, "trace_graph", lambda compiled, tracer: compiled)
    monkeypatch.setattr(runner_mod, "get_tracer", lambda *args, **kwargs: SimpleNamespace(flush=lambda: None))
    monkeypatch.setattr(runner_mod, "get_settings", lambda: SimpleNamespace(privacy_mode=True, scout_model="test"))
    monkeypatch.setattr(
        runner_mod,
        "attach_cv",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("attachment attempted")),
    )

    list(stream_search(sample_profile, cv_path="resume.pdf", thread_id="privacy", tags=["test"]))


def test_privacy_mode_blocks_cv_attachment_inside_tracing(monkeypatch):
    monkeypatch.setattr(tracing_mod, "get_settings", lambda: SimpleNamespace(privacy_mode=True))
    tracer = SimpleNamespace(
        created_traces=lambda: (_ for _ in ()).throw(AssertionError("trace inspected")),
    )

    tracing_mod.attach_cv(tracer, "resume.pdf")


def test_candidate_name_is_not_sent_to_ranking_prompt(sample_profile):
    rendered = _render_profile(sample_profile)

    assert sample_profile.name not in rendered
    assert "Name:" not in rendered
    assert "Skills:" in rendered


def test_upload_cleanup_refuses_paths_outside_temp(monkeypatch):
    temp_root = Path(__file__).parent / ".privacy-temp"
    outside = Path(__file__).resolve()
    monkeypatch.setattr("job_scout.privacy.tempfile.gettempdir", lambda: str(temp_root))

    assert delete_temporary_upload(outside) is False
    assert outside.exists()


def test_upload_cleanup_deletes_file_inside_temp(monkeypatch):
    temp_root = Path(__file__).parent / ".privacy-temp"
    upload = temp_root / "gradio" / "resume.pdf"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"temporary")
    monkeypatch.setattr("job_scout.privacy.tempfile.gettempdir", lambda: str(temp_root))

    assert delete_temporary_upload(upload) is True
    assert not upload.exists()
    upload.parent.rmdir()
    temp_root.rmdir()
