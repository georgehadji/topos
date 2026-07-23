"""Settings from environment. See .env.example. Slice 0.3."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOPOS_", env_file=".env", extra="ignore")

    db_dsn: str = Field(default="postgresql://topos:devonly@localhost:5432/topos")
    s3_endpoint: str = Field(default="http://localhost:9000")
    s3_access_key: str = Field(default="topos")
    s3_secret_key: str = Field(default="devonlydevonly")
    s3_bucket: str = Field(default="topos-artifacts")

    llm_provider: str = Field(default="unset")
    llm_api_key: str = Field(default="")
    llm_base_url: str = Field(default="https://openrouter.ai/api/v1")
    llm_model: str = Field(default="mistralai/mistral-large-2512")
    llm_monthly_budget_eur: float = Field(default=250.0)

    log_level: str = Field(default="INFO")

    # OIDC auth (slice 1.11)
    oidc_discovery_url: str = Field(default="")
    oidc_client_id: str = Field(default="")
    oidc_client_secret: str = Field(default="")


def get_settings() -> Settings:
    return Settings()
