"""Application configuration via pydantic-settings.

A single flat ``Settings`` object holds every knob. Env var names match the
project spec (``SCOUT_MODEL``, ``OPENAI_API_KEY``, ``ADZUNA_APP_ID``, ...) so a
reader can copy ``.env.example`` to ``.env`` and be running. Secrets use
``SecretStr`` so they never render in logs or trace metadata by accident.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read once from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Models (LangChain init_chat_model provider strings) ------------------
    # Default is OpenAI gpt-4o-mini so Opik can attribute real cost. Swap to a
    # free provider by setting SCOUT_MODEL (e.g. "groq:llama-3.3-70b-versatile"
    # or "ollama:llama3.2"). See .env.example.
    scout_model: str = Field(default="openai:gpt-4o-mini", alias="SCOUT_MODEL")
    # Tailoring uses a possibly stronger model in Phase 2; present now, unused.
    scout_tailor_model: str = Field(default="openai:gpt-4o-mini", alias="SCOUT_TAILOR_MODEL")

    # --- LLM provider keys ----------------------------------------------------
    openai_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENAI_API_KEY")

    # --- Opik observability ---------------------------------------------------
    opik_api_key: SecretStr = Field(default=SecretStr(""), alias="OPIK_API_KEY")
    opik_workspace: str = Field(default="", alias="OPIK_WORKSPACE")
    opik_project_name: str = Field(default="job-scout", alias="OPIK_PROJECT_NAME")
    # Master switch: tests and offline runs set this false to skip all Opik I/O.
    opik_enabled: bool = Field(default=True, alias="OPIK_ENABLED")

    # --- Jobs data sources ----------------------------------------------------
    adzuna_app_id: SecretStr = Field(default=SecretStr(""), alias="ADZUNA_APP_ID")
    adzuna_app_key: SecretStr = Field(default=SecretStr(""), alias="ADZUNA_APP_KEY")

    # --- Cross-cutting guardrails --------------------------------------------
    max_llm_calls_per_run: int = Field(default=25, alias="MAX_LLM_CALLS_PER_RUN")

    # --- Convenience accessors ------------------------------------------------
    @property
    def has_adzuna(self) -> bool:
        return bool(self.adzuna_app_id.get_secret_value() and self.adzuna_app_key.get_secret_value())

    @property
    def has_opik(self) -> bool:
        return self.opik_enabled and bool(self.opik_api_key.get_secret_value())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
