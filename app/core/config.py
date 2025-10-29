from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/briefing"
    youtube_api_key: str | None = None
    transcript_max_retry: int = 6
    transcript_backoff_minutes: int = 5
    transcript_max_concurrency: int = 2
    transcript_min_interval_ms: int = 500
    summary_max_retry: int = 5
    notify_max_retry: int = 5
    email_smtp_url: str | None = None
    email_from: str | None = None
    webhook_secret: str | None = None
    webhook_callback_url: str = "http://localhost:8000/webhooks/youtube"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", env_file_encoding="utf-8")

@lru_cache

def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
