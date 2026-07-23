"""Tests for the cross-platform one-command launcher."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.start as start


def test_ensure_env_file_creates_once_without_overwrite(monkeypatch):
    temp_root = Path(__file__).parent / ".start-env"
    example = temp_root / ".env.example"
    target = temp_root / ".env"
    temp_root.mkdir()
    try:
        example.write_text("SCOUT_MODEL=ollama:test\n", encoding="utf-8")
        monkeypatch.setattr(start, "ENV_EXAMPLE", example)
        monkeypatch.setattr(start, "ENV_FILE", target)

        assert start.ensure_env_file() is True
        assert target.read_text(encoding="utf-8") == "SCOUT_MODEL=ollama:test\n"
        target.write_text("CUSTOM=true\n", encoding="utf-8")
        assert start.ensure_env_file() is False
        assert target.read_text(encoding="utf-8") == "CUSTOM=true\n"
    finally:
        target.unlink(missing_ok=True)
        example.unlink(missing_ok=True)
        temp_root.rmdir()


def test_environment_overrides_dotenv(monkeypatch):
    target = Path(__file__).parent / ".start-env-file"
    try:
        target.write_text("SCOUT_MODEL=ollama:from-file\n", encoding="utf-8")
        monkeypatch.setattr(start, "ENV_FILE", target)
        monkeypatch.setenv("SCOUT_MODEL", "ollama:from-process")

        assert start._read_env_value("SCOUT_MODEL") == "ollama:from-process"
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("ollama:qwen3:8b", "qwen3:8b"),
        ("OLLAMA:gemma3:4b", "gemma3:4b"),
        ("openai:gpt-4o-mini", None),
        ("ollama:", None),
    ],
)
def test_ollama_model_name(setting, expected):
    assert start._ollama_model_name(setting) == expected


def test_installed_ollama_model_is_not_pulled(monkeypatch):
    calls = []
    monkeypatch.setattr(start.shutil, "which", lambda name: "/bin/ollama")
    monkeypatch.setattr(
        start,
        "_run",
        lambda command, capture=False: calls.append(command)
        or SimpleNamespace(stdout="NAME ID SIZE\nqwen3:8b abc 5 GB\n"),
    )

    start.ensure_ollama_model("ollama:qwen3:8b", pull_missing=True)

    assert calls == [["/bin/ollama", "list"]]


def test_missing_ollama_model_is_pulled(monkeypatch):
    calls = []
    monkeypatch.setattr(start.shutil, "which", lambda name: "/bin/ollama")

    def fake_run(command, capture=False):
        calls.append(command)
        return SimpleNamespace(stdout="NAME ID SIZE\n")

    monkeypatch.setattr(start, "_run", fake_run)

    start.ensure_ollama_model("ollama:qwen3:8b", pull_missing=True)

    assert calls == [["/bin/ollama", "list"], ["/bin/ollama", "pull", "qwen3:8b"]]


def test_missing_model_can_fail_without_download(monkeypatch):
    monkeypatch.setattr(start.shutil, "which", lambda name: "/bin/ollama")
    monkeypatch.setattr(start, "_run", lambda command, capture=False: SimpleNamespace(stdout="NAME ID SIZE\n"))

    with pytest.raises(start.StartError, match="ollama pull qwen3:8b"):
        start.ensure_ollama_model("ollama:qwen3:8b", pull_missing=False)


def test_unreachable_ollama_service_has_actionable_error(monkeypatch):
    monkeypatch.setattr(start.shutil, "which", lambda name: "/bin/ollama")
    error = subprocess.CalledProcessError(1, ["ollama", "list"], stderr="connection refused")
    monkeypatch.setattr(start, "_run", lambda command, capture=False: (_ for _ in ()).throw(error))

    with pytest.raises(start.StartError, match="not reachable"):
        start.ensure_ollama_model("ollama:qwen3:8b", pull_missing=True)


def test_main_check_runs_setup_without_launch(monkeypatch):
    calls = []
    monkeypatch.setattr(start.shutil, "which", lambda name: "uv")
    monkeypatch.setattr(start, "ensure_env_file", lambda: False)
    monkeypatch.setattr(start, "sync_dependencies", lambda uv: calls.append(("sync", uv)))
    monkeypatch.setattr(start, "_read_env_value", lambda *args: "openai:gpt-4o-mini")
    monkeypatch.setattr(start, "ensure_cloud_model", lambda model: calls.append(("cloud", model)))
    monkeypatch.setattr(start, "launch", lambda uv: (_ for _ in ()).throw(AssertionError("launch called")))

    assert start.main(["--check"]) == 0
    assert calls == [("sync", "uv"), ("cloud", "openai:gpt-4o-mini")]


def test_dependency_sync_installs_all_provider_extras(monkeypatch):
    calls = []
    monkeypatch.setattr(start, "_run", lambda command, capture=False: calls.append(command))

    start.sync_dependencies("uv")

    assert calls == [["uv", "sync", "--all-extras", "--all-groups"]]


def test_shell_wrappers_reference_shared_launcher():
    root = Path(__file__).resolve().parents[1]

    assert "scripts/start.py" in (root / "start.ps1").read_text(encoding="utf-8")
    assert "scripts/start.py" in (root / "start.sh").read_text(encoding="utf-8")
    assert "start.sh" in (root / "start.command").read_text(encoding="utf-8")


def test_cloud_launcher_requires_offline_disabled(monkeypatch):
    values = {
        "OFFLINE_MODE": "true",
        "CLOUD_LLM_ENABLED": "true",
        "OPENAI_API_KEY": "configured",
    }
    monkeypatch.setattr(start, "_read_env_value", lambda name, default="": values.get(name, default))

    with pytest.raises(start.StartError, match="OFFLINE_MODE=false"):
        start.ensure_cloud_model("openai:gpt-5-mini")


def test_cloud_launcher_requires_explicit_consent(monkeypatch):
    values = {
        "OFFLINE_MODE": "false",
        "CLOUD_LLM_ENABLED": "false",
        "ANTHROPIC_API_KEY": "configured",
    }
    monkeypatch.setattr(start, "_read_env_value", lambda name, default="": values.get(name, default))

    with pytest.raises(start.StartError, match="CLOUD_LLM_ENABLED=true"):
        start.ensure_cloud_model("anthropic:claude-sonnet-4-6")


def test_cloud_launcher_requires_matching_key(monkeypatch):
    values = {
        "OFFLINE_MODE": "false",
        "CLOUD_LLM_ENABLED": "true",
        "XAI_API_KEY": "",
    }
    monkeypatch.setattr(start, "_read_env_value", lambda name, default="": values.get(name, default))

    with pytest.raises(start.StartError, match="XAI_API_KEY"):
        start.ensure_cloud_model("xai:grok-4.3")


@pytest.mark.parametrize(
    "model",
    ["openai:gpt-5-mini", "anthropic:claude-sonnet-4-6", "xai:grok-4.3"],
)
def test_cloud_launcher_accepts_supported_provider(monkeypatch, model):
    values = {
        "OFFLINE_MODE": "false",
        "CLOUD_LLM_ENABLED": "true",
        "OPENAI_API_KEY": "configured",
        "ANTHROPIC_API_KEY": "configured",
        "XAI_API_KEY": "configured",
    }
    monkeypatch.setattr(start, "_read_env_value", lambda name, default="": values.get(name, default))

    start.ensure_cloud_model(model)
