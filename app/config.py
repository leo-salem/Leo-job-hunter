from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: str = "local"
    log_level: str = "INFO"
    timezone: str = "Africa/Cairo"
    daily_run_hour: int = 0
    daily_run_minute: int = 0

    # Database (async URL used by app; sync URL used by Alembic + Celery)
    database_url: str = "postgresql+asyncpg://jobhunter:changeme@postgres:5432/jobhunter"
    sync_database_url: str = "postgresql+psycopg://jobhunter:changeme@postgres:5432/jobhunter"

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    ai_enabled: bool = True
    ai_max_jobs_per_run: int = 80

    # HTTP
    http_timeout_seconds: int = 30
    http_max_retries: int = 4
    http_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Playwright / Wellfound
    wellfound_enabled: bool = False
    playwright_headless: bool = True

    # Catchup
    catchup_threshold_hours: int = 20

    # Resume
    resume_summary: str = Field(default="")

    @property
    def ai_ready(self) -> bool:
        return self.ai_enabled and bool(self.anthropic_api_key)

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
