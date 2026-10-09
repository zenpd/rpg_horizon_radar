"""Central configuration — reads from .env via pydantic-settings.

Secrets that live in Azure Key Vault are declared as ``*_kv_uri`` fields.
The ``_resolve_kv_secrets`` validator fetches the real values at startup so the
rest of the app reads plain fields (e.g. ``settings.azure_openai_api_key``) with
no knowledge of Key Vault.

This is the accelerator baseline — add app-specific settings in the
"App-specific settings" block at the bottom; keep the platform blocks intact.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ────────────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_secret_key: str = "change-me"
    log_level: str = "INFO"
    # Comma-separated allowed origins for non-development environments, e.g.
    # "https://rpg-horizon-radar-fe.bravesky-d9f9eeb7.eastus2.azurecontainerapps.io"
    cors_allowed_origins: str = ""

    # ── Database / Cache ───────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/rpg_horizon_radar"
    redis_url: str = "redis://localhost:6379/0"

    # ── Azure OpenAI ───────────────────────────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_api_version: str = "2025-01-01-preview"

    # ── Azure Key Vault ────────────────────────────────────────────────────────
    azure_keyvault_url: str = "https://zaf-kv-01.vault.azure.net/"

    # KV URI overrides — when set, the corresponding plain field is populated at
    # startup by _resolve_kv_secrets below.
    azure_openai_endpoint_kv_uri: str = ""
    azure_openai_api_key_kv_uri: str = ""
    azure_openai_deployment_kv_uri: str = ""
    database_url_kv_uri: str = ""
    redis_url_kv_uri: str = ""

    # ── Azure / EntraID ────────────────────────────────────────────────────────
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    entra_authority: str = "https://login.microsoftonline.com/"
    entra_audience: str = ""

    # ── Vector DB (optional) ───────────────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # ── Temporal ───────────────────────────────────────────────────────────────
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "rpg-horizon-radar"
    temporal_task_queue_agents: str = "rpg-horizon-radar-agents"

    # ── Arize Phoenix Observability ────────────────────────────────────────────
    # Set false for local dev / CI without a Phoenix collector running: skips exporter setup
    # entirely, rather than configuring one that retries forever in the background (noisy logs).
    tracing_enabled: bool = True
    phoenix_host: str = "localhost"
    phoenix_port: int = 6006
    # e.g. https://zaf-phoenix.bravesky-d9f9eeb7.eastus2.azurecontainerapps.io/v1/traces
    phoenix_collector_endpoint: str = ""
    phoenix_project_name: str = "rpg-horizon-radar"
    arize_phoenix_api_key: str = ""          # resolved from KV
    arize_phoenix_api_key_kv_uri: str = ""

    # ── Prompts ────────────────────────────────────────────────────────────────
    prompts_dir: str = "config/prompts"

    # ────────────────────────────────────────────────────────────────────────────
    # App-specific settings — add your own fields below (external APIs, feature
    # flags, thresholds, etc). Declare a matching ``*_kv_uri`` and add it to the
    # kv_map in _resolve_kv_secrets for any secret sourced from Key Vault.
    # ────────────────────────────────────────────────────────────────────────────

    # Minimum OpportunityScore (0-100) for a signal cluster to be included in a
    # compiled weekly digest. See services/scoring.py and services/digest.py.
    digest_threshold: float = 65.0

    # ── Live signal connectors (ingestion/connectors/live/) ────────────────────
    # A connector runs only when its key is set. Each one's quota and pacing is
    # described in its module docstring.
    live_connectors_enabled: bool = True
    gnews_api_key: str = ""
    newsdata_api_key: str = ""
    tavily_api_key: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    fetchlayer_api_key: str = ""          # Glassdoor employee ratings
    youtube_api_key: str = ""
    alpha_vantage_api_key: str = ""       # ticker lookup only, 25 calls a day
    epo_ops_consumer_key: str = ""
    epo_ops_consumer_secret: str = ""
    fincrux_api_key: str = ""             # 5 calls a day
    nse_enabled: bool = True              # no key; NSE's site API, used sparingly

    # KV URI overrides for every connector key above — every one of these was pasted into chat
    # during the build and needs rotating; set the corresponding *_KV_URI once rotated and the
    # plain field is populated from Key Vault at startup, same as azure_openai_api_key below.
    gnews_api_key_kv_uri: str = ""
    newsdata_api_key_kv_uri: str = ""
    tavily_api_key_kv_uri: str = ""
    adzuna_app_id_kv_uri: str = ""
    adzuna_app_key_kv_uri: str = ""
    fetchlayer_api_key_kv_uri: str = ""
    youtube_api_key_kv_uri: str = ""
    alpha_vantage_api_key_kv_uri: str = ""
    epo_ops_consumer_key_kv_uri: str = ""
    epo_ops_consumer_secret_kv_uri: str = ""
    fincrux_api_key_kv_uri: str = ""

    # ── Reasoning LLM routes (shared/llm_chat.py) ──────────────────────────────
    # Used for watchlist discovery and SWOT briefs — never for scoring.
    groq_api_key: str = ""
    nvidia_api_key: str = ""
    groq_api_key_kv_uri: str = ""
    nvidia_api_key_kv_uri: str = ""
    llm_routes: str = "groq:openai/gpt-oss-120b,nvidia:nvidia/nemotron-3-super-120b-a12b"
    llm_reasoning_effort: str = "low"

    # ── Watchlist discovery + scheduler (services/discovery.py, scheduler.py) ──
    # Discovered companies are always proposed, never watched, until a
    # compliance_admin approves them; there is deliberately no auto-approve.
    scheduler_enabled: bool = True
    ingest_daily_at: str = "17:00"        # local time
    discovery_every_days: int = 7
    digest_every_days: int = 7            # services/digest.py — weekly M&A-signal digest
    auto_swot: bool = True                # rebuild a subsidiary's SWOT after its signals change

    # ── Security validators ────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _enforce_secret_key(self) -> "Settings":
        """Refuse to start in production with the default secret key."""
        if self.app_env == "production" and self.app_secret_key == "change-me":
            raise ValueError(
                "app_secret_key must not be 'change-me' in production. "
                "Set APP_SECRET_KEY via Azure Key Vault or an environment variable."
            )
        return self

    @model_validator(mode="after")
    def _resolve_kv_secrets(self) -> "Settings":
        """Replace any field whose corresponding ``*_kv_uri`` is set with the
        secret value fetched from Azure Key Vault. Silent no-op when the Azure
        SDK is not installed (local dev)."""
        try:
            from security.vault import get_secret_by_uri
        except ImportError:
            return self

        kv_map: list[tuple[str, str]] = [
            ("azure_openai_endpoint_kv_uri", "azure_openai_endpoint"),
            ("azure_openai_api_key_kv_uri", "azure_openai_api_key"),
            ("azure_openai_deployment_kv_uri", "azure_openai_deployment"),
            ("database_url_kv_uri", "database_url"),
            ("redis_url_kv_uri", "redis_url"),
            ("arize_phoenix_api_key_kv_uri", "arize_phoenix_api_key"),
            ("gnews_api_key_kv_uri", "gnews_api_key"),
            ("newsdata_api_key_kv_uri", "newsdata_api_key"),
            ("tavily_api_key_kv_uri", "tavily_api_key"),
            ("adzuna_app_id_kv_uri", "adzuna_app_id"),
            ("adzuna_app_key_kv_uri", "adzuna_app_key"),
            ("fetchlayer_api_key_kv_uri", "fetchlayer_api_key"),
            ("youtube_api_key_kv_uri", "youtube_api_key"),
            ("alpha_vantage_api_key_kv_uri", "alpha_vantage_api_key"),
            ("epo_ops_consumer_key_kv_uri", "epo_ops_consumer_key"),
            ("epo_ops_consumer_secret_kv_uri", "epo_ops_consumer_secret"),
            ("fincrux_api_key_kv_uri", "fincrux_api_key"),
            ("groq_api_key_kv_uri", "groq_api_key"),
            ("nvidia_api_key_kv_uri", "nvidia_api_key"),
        ]
        for uri_field, target_field in kv_map:
            uri: str = getattr(self, uri_field, "")
            if uri:
                value = get_secret_by_uri(uri)
                if value:
                    object.__setattr__(self, target_field, value)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
