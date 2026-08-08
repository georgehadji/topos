"""Settings from environment. See .env.example. Slice 0.3."""

from __future__ import annotations

from pydantic import AliasChoices, Field, model_validator
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

    # Vendor-standard names, accepted unprefixed because that is how these keys
    # are normally pasted into a .env. See _prefer_real_keys below.
    openrouter_api_key: str = Field(default="", validation_alias=AliasChoices("OPENROUTER_API_KEY"))

    # Perplexity direct. Preferred over OpenRouter for Sonar: the direct API
    # returns `citations` / `search_results`, which gateways strip.
    perplexity_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("TOPOS_PERPLEXITY_API_KEY", "PERPLEXITY_API_KEY"),
    )
    perplexity_base_url: str = Field(default="https://api.perplexity.ai")
    perplexity_model: str = Field(default="sonar-pro")

    # xAI direct (primary for Grok models; OpenRouter is the fallback)
    xai_api_key: str = Field(
        default="", validation_alias=AliasChoices("TOPOS_XAI_API_KEY", "XAI_API_KEY")
    )
    xai_base_url: str = Field(default="https://api.x.ai/v1")
    # Single source of truth for the Grok model name. xai.py's own default
    # exists only for tests that construct XaiProvider() directly — every
    # production construction site (interfaces/cli/main.py) must pass this.
    xai_model: str = Field(default="grok-4.5")
    llm_fallback_model: str = Field(default="")  # OpenRouter slug e.g. "x-ai/grok-4.5"

    # ── Web search engines (adapters/sources/websearch.py) ───────────────────
    # Every engine with a key configured is queried by the `websearch` source.
    # All optional: leave blank to disable that engine.
    brave_api_key: str = Field(default="")
    google_cse_api_key: str = Field(default="")
    google_cse_cx: str = Field(default="")  # Programmable Search engine id
    bing_api_key: str = Field(default="")
    tavily_api_key: str = Field(default="")
    serper_api_key: str = Field(default="")
    searxng_base_url: str = Field(default="")  # self-hosted, needs no key

    # ── Search reranking (adapters/rerank, ADR-013) ──────────────────────────
    rerank_enabled: bool = Field(default=True)
    # Comma-separated OpenRouter model slugs, tried in order. Token-priced
    # models beat Cohere's flat per-search rate at Topos' candidate counts —
    # see docs/adr/ADR-013 for the comparison.
    rerank_models: str = Field(
        default="voyageai/rerank-2.5-lite,nvidia/llama-nemotron-rerank-vl-1b-v2:free"
    )
    rerank_candidates: int = Field(default=50)

    # ── LLM model cascade (adapters/llm/cascade.py, Phase 6 #6.5) ────────────
    # Comma-separated, cheapest first. Empty (the default) disables the
    # cascade — build_llm_client() then uses llm_model unchanged. Mirrors the
    # rerank_models convention: a table someone opts into, not a flag that
    # silently changes model selection.
    llm_cascade_models: str = Field(default="")

    log_level: str = Field(default="INFO")

    @model_validator(mode="after")
    def _prefer_real_keys(self) -> Settings:
        """A real key always beats a placeholder, whichever name it arrived under.

        `.env` files in this project have historically carried a dummy
        ``TOPOS_LLM_API_KEY``. If a genuine ``OPENROUTER_API_KEY`` is also
        present, that is plainly the one the operator meant to use.
        """
        if is_placeholder_key(self.llm_api_key) and not is_placeholder_key(self.openrouter_api_key):
            self.llm_api_key = self.openrouter_api_key
        return self

    # MCP server auth
    mcp_api_key: str = Field(default="")

    # OIDC auth (slice 1.11)
    oidc_discovery_url: str = Field(default="")
    oidc_client_id: str = Field(default="")
    oidc_client_secret: str = Field(default="")


def get_settings() -> Settings:
    return Settings()


# Keys that look set but are the committed dev placeholders. Kept in one place
# so the worker and `topos-cli health` can never disagree about whether
# extraction is running for real.
_PLACEHOLDER_KEY_PREFIXES = ("sk-or-v1-aeef18", "devonly", "unset")


def is_placeholder_key(key: str) -> bool:
    """True when *key* is missing or is a known placeholder.

    NB: never add "" to the prefix tuple — str.startswith("") is True for every
    string, which would silently force the mock everywhere.
    """
    return not key or key.startswith(_PLACEHOLDER_KEY_PREFIXES)
