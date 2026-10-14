"""Application configuration.

All configuration is environment-driven (prefix ``CLOUDOPS_``). Secrets are
backend-only and never serialized into API responses.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLOUDOPS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "CloudOps AI Agent"
    version: str = "0.1.0"
    environment: str = "development"

    # --- Modes -----------------------------------------------------------
    # Demo mode serves clearly-labeled synthetic data and requires no cloud
    # credentials. Live providers are opt-in and read-only.
    demo_mode: bool = True
    gcp_enabled: bool = False
    aws_enabled: bool = False

    # Explicit allowlists — live mode fails closed when empty.
    gcp_allowed_projects: str = ""  # comma-separated project IDs
    aws_allowed_accounts: str = ""  # comma-separated account IDs
    aws_region: str = "us-east-1"

    # --- LLM -------------------------------------------------------------
    llm_provider: str = "mock"  # "mock" | "gemini"
    gemini_api_key: str = ""  # backend-only; never exposed via the API
    # Stable GA Flash model as of 2026-10 (2.x series retired; gemini-3.7-flash
    # deprecated 2026-10-08). Override with CLOUDOPS_GEMINI_MODEL; verify
    # availability against your API key.
    gemini_model: str = "gemini-3.8-flash"

    # --- Agent limits ----------------------------------------------------
    max_steps: int = Field(default=8, ge=1, le=20)
    tool_timeout_seconds: int = Field(default=20, ge=1, le=120)
    investigation_timeout_seconds: int = Field(default=120, ge=10, le=600)
    tool_retry_budget: int = Field(default=2, ge=0, le=5)
    log_query_max_limit: int = Field(default=500, ge=1, le=2000)
    max_evidence_payload_bytes: int = Field(default=64_000, ge=1_000)

    # --- HTTP / security --------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    rate_limit_per_minute: int = Field(default=240, ge=1)
    investigations_rate_limit_per_minute: int = Field(default=12, ge=1)

    # --- Persistence -----------------------------------------------------
    db_path: str = str(BACKEND_DIR / "data" / "cloudops.db")

    @field_validator("llm_provider")
    @classmethod
    def _validate_llm_provider(cls, v: str) -> str:
        if v not in {"mock", "gemini"}:
            raise ValueError("llm_provider must be 'mock' or 'gemini'")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def gcp_allowed_project_list(self) -> list[str]:
        return [p.strip() for p in self.gcp_allowed_projects.split(",") if p.strip()]

    @property
    def aws_allowed_account_list(self) -> list[str]:
        return [a.strip() for a in self.aws_allowed_accounts.split(",") if a.strip()]

    @property
    def llm_model_label(self) -> str:
        return self.gemini_model if self.llm_provider == "gemini" else "deterministic-v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
