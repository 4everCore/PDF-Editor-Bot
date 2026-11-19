"""Validated application configuration; secrets are never logged."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr = SecretStr("")
    database_url: str = "sqlite+aiosqlite:///./pdfbot.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_root: Path = Path("./data/files")
    temp_root: Path = Path("./tmp")
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=2 * 1024**3)
    max_pdf_pages: int = Field(default=500, ge=1, le=10000)
    max_concurrent_jobs: int = Field(default=2, ge=1, le=100)
    job_timeout_seconds: int = Field(default=180, ge=1, le=3600)
    file_ttl_hours: int = Field(default=24, ge=1, le=8760)
    rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)
    log_level: str = "INFO"
    default_language: str = "fa"
    ai_provider: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: SecretStr = SecretStr("")
    ai_model: str = ""

    @field_validator("default_language")
    @classmethod
    def supported_language(cls, value: str) -> str:
        if value not in {"fa", "en"}:
            raise ValueError("default_language must be 'fa' or 'en'")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
