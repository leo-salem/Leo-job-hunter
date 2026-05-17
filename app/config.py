from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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

    # Daily scrape concurrency. With 4, up to 4 companies are processed
    # simultaneously. Lower if LinkedIn/Wuzzuf start rate-limiting; raise
    # if your DB pool can handle more (pool_size + max_overflow = 20).
    daily_concurrency: int = 4

    # Per-source concurrency caps. These layer on top of daily_concurrency
    # so that even if 4 global slots are free, at most N of them go to the
    # same rate-limited source. Sources not listed (greenhouse / lever /
    # ashby) use only daily_concurrency.
    linkedin_concurrency: int = 1   # LinkedIn guest endpoint is the most rate-limited
    wuzzuf_concurrency: int = 2
    bayt_concurrency: int = 2
    workday_concurrency: int = 2
    wellfound_concurrency: int = 1

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
