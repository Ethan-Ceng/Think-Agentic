#!/usr/bin/env python
# -*- coding: utf-8 -*-
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    env: str = "development"
    log_level: str = "INFO"
    app_config_filepath: str = "config.yaml"
    run_migrations_on_startup: bool = False
    auth_secret_key: str = "change-me-in-production"
    auth_access_token_ttl_seconds: int = 60 * 60 * 24 * 7
    auth_registration_enabled: bool = True

    sqlalchemy_database_uri: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/manus"

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_region: str = ""
    cos_scheme: str = "https"
    cos_bucket: str = ""
    cos_domain: str = ""

    sandbox_address: str | None = None
    sandbox_image: str | None = "manus-sandbox"
    sandbox_name_prefix: str | None = "manus-sandbox"
    sandbox_ttl_minutes: int | None = 60
    sandbox_network: str | None = "manus-network"
    sandbox_chrome_args: str | None = ""
    sandbox_https_proxy: str | None = None
    sandbox_http_proxy: str | None = None
    sandbox_no_proxy: str | None = None

    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
