"""Application settings.

The environment-variable contract is frozen in docs/01_architecture/architecture.md §6.
Values never appear in code or docs; secrets only via environment (NFR6).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["glm", "openai", "gemini", "anthropic", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Business Risk"
    app_version: str = "0.1.0"

    database_url: str = "postgresql+psycopg://abr:abr@localhost:5432/abr"

    llm_provider: ProviderName = "glm"
    glm_api_key: str = ""
    glm_model: str = "glm-5.3-flash"
    glm_base_url: str = "https://api.z.ai/api/paas/v4"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = ""

    fred_api_key: str = ""

    # EDGAR secondary ingestion (frozen data.md FD-2: feature-flagged, off by default)
    enable_edgar: bool = False
    edgar_user_agent: str = "AI-Business-Risk-Research contact@example.com"

    data_cache_dir: str = "data/raw"

    run_budget_tokens: int = 200_000
    run_timeout_seconds: int = 600

    log_level: str = "INFO"
    run_live_smoke: bool = False

    @property
    def llm_configured(self) -> bool:
        """True when the selected provider has the credentials it needs."""
        if self.llm_provider == "ollama":
            return bool(self.ollama_base_url)
        return any(
            (
                self.glm_api_key,
                self.openai_api_key,
                self.gemini_api_key,
                self.anthropic_api_key,
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
