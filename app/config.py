from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database (Railway provides postgresql://, we need postgresql+asyncpg://)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/restaurant_intel"

    @property
    def async_database_url(self) -> str:
        """Get database URL with asyncpg driver."""
        url = self.database_url
        # Railway provides postgresql://, convert to postgresql+asyncpg://
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # Application
    app_env: str = "development"
    debug: bool = True

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS
    cors_origins: str = "http://localhost:3000"

    # LLM Settings (OpenRouter)
    llm_enabled: bool = True
    llm_model: str = "bytedance-seed/seed-1.6"
    llm_api_base: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""  # Set via OPENROUTER_API_KEY env var

    # Tier Calculation Settings
    tier_lookback_days: int = 30
    tier_recalc_day: int = 0  # 0=Monday, 6=Sunday

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    # Google AI (for chatbot)
    google_api_key: str | None = None
    gemini_model: str = "gemini-3-flash"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
