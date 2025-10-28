from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/briefing"
    youtube_api_key: str | None = None
    watch_channels: Annotated[list[str], Field(default_factory=list)]
    poll_interval_minutes: int = 15

    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", env_file_encoding="utf-8")

    @field_validator("watch_channels", mode="before")
    @classmethod
    def split_channels(cls, value: str | list[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache

def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
