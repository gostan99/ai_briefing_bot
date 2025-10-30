from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/briefing"
    youtube_api_key: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_max_chars: int = 12000
    openai_base_url: str | None = None
    transcript_max_retry: int = 6
    transcript_backoff_minutes: int = 5
    transcript_max_concurrency: int = 2
    transcript_min_interval_ms: int = 500
    summary_max_retry: int = 5
    metadata_max_retry: int = 4
    metadata_backoff_minutes: int = 5
    dashboard_cors_origins: list[str] = ["http://localhost:5173"]
    webhook_secret: str | None = None
    webhook_callback_url: str = "http://localhost:8000/webhooks/youtube"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", env_file_encoding="utf-8")

    @field_validator("dashboard_cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

@lru_cache

def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
