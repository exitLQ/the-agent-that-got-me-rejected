"""Cross-platform first-run setup and application launcher."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


class StartError(RuntimeError):
    """An actionable startup failure."""


def _read_env_value(name: str, default: str = "") -> str:
    """Read a setting from the process environment or the project ``.env``."""
    if name in os.environ:
        return os.environ[name].strip()
    if not ENV_FILE.exists():
        return default
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().casefold() == name.casefold():
            return value.strip().strip("\"'")
    return default


def ensure_env_file() -> bool:
    """Create ``.env`` from the example without overwriting user configuration."""
    if ENV_FILE.exists():
        return False
    if not ENV_EXAMPLE.exists():
        raise StartError(f"Configuration template not found: {ENV_EXAMPLE}")
    shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
    return True


def _run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run one checked command from the repository root."""
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )


def sync_dependencies(uv: str) -> None:
    """Install the locked application and local Ollama integration."""
    _run([uv, "sync", "--extra", "ollama", "--all-groups"])


def _ollama_model_name(model_setting: str) -> str | None:
    """Return the Ollama tag from a provider-qualified model setting."""
    provider, separator, model = model_setting.partition(":")
    if separator and provider.casefold() == "ollama" and model.strip():
        return model.strip()
    return None


def ensure_ollama_model(model_setting: str, *, pull_missing: bool) -> None:
    """Check the Ollama service and optionally pull a missing configured model."""
    model = _ollama_model_name(model_setting)
    if model is None:
        return
    ollama = shutil.which("ollama")
    if ollama is None:
        raise StartError(
            "Ollama is required by SCOUT_MODEL but was not found. "
            "Install it from https://ollama.com/download and run this launcher again."
        )
    try:
        result = _run([ollama, "list"], capture=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        suffix = f" Details: {detail}" if detail else ""
        raise StartError(f"Ollama is installed but its service is not reachable.{suffix}") from exc

    installed = {
        line.split(maxsplit=1)[0].casefold()
        for line in result.stdout.splitlines()[1:]
        if line.strip()
    }
    if model.casefold() in installed:
        return
    if not pull_missing:
        raise StartError(f"Ollama model '{model}' is missing. Run: ollama pull {model}")
    print(f"Pulling missing Ollama model: {model}", flush=True)
    try:
        _run([ollama, "pull", model])
    except subprocess.CalledProcessError as exc:
        raise StartError(f"Could not pull Ollama model '{model}'.") from exc


def launch(uv: str) -> int:
    """Launch the Gradio application and preserve its exit status."""
    try:
        completed = subprocess.run(
            [uv, "run", "python", "-m", "job_scout.app"],
            cwd=ROOT,
            check=False,
        )
    except KeyboardInterrupt:
        return 130
    return completed.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse launcher options."""
    parser = argparse.ArgumentParser(description="Set up and launch the-agent-that-got-me-rejected.")
    parser.add_argument("--skip-sync", action="store_true", help="Do not run uv sync before startup.")
    parser.add_argument(
        "--skip-model-pull",
        action="store_true",
        help="Fail with a command instead of downloading a missing Ollama model.",
    )
    parser.add_argument("--check", action="store_true", help="Run setup and prerequisite checks without launching the app.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Prepare the project and launch the application."""
    args = parse_args(argv)
    uv = shutil.which("uv")
    if uv is None:
        print(
            "Startup failed: uv was not found. Install it from "
            "https://docs.astral.sh/uv/getting-started/installation/ and run this launcher again.",
            file=sys.stderr,
        )
        return 1
    try:
        created = ensure_env_file()
        if created:
            print("Created .env from .env.example.", flush=True)
        if not args.skip_sync:
            print("Installing locked dependencies with uv.", flush=True)
            sync_dependencies(uv)
        model_setting = _read_env_value("SCOUT_MODEL", "ollama:qwen3:8b")
        ensure_ollama_model(model_setting, pull_missing=not args.skip_model_pull)
    except (StartError, subprocess.CalledProcessError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1

    if args.check:
        print("Startup checks passed.", flush=True)
        return 0
    print("Starting the application at http://localhost:7860", flush=True)
    return launch(uv)


if __name__ == "__main__":
    raise SystemExit(main())
