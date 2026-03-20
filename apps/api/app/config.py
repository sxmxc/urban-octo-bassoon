from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    log_level: str = Field(default="info", validation_alias="API_LOG_LEVEL")
    app_version: str = Field(default="2.0.0-alpha.1", validation_alias="APP_VERSION")

    postgres_user: str = Field(default="mockadmin", validation_alias="POSTGRES_USER")
    postgres_password: str = Field(default="mockpassword", validation_alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="mockapi", validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="postgres", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")

    admin_bootstrap_username: str = Field(
        default="admin",
        validation_alias=AliasChoices("ADMIN_BOOTSTRAP_USERNAME", "ADMIN_USERNAME"),
    )
    admin_bootstrap_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ADMIN_BOOTSTRAP_PASSWORD", "ADMIN_PASSWORD"),
    )
    admin_password_min_length: int = Field(default=12, validation_alias="ADMIN_PASSWORD_MIN_LENGTH")
    admin_login_max_attempts: int = Field(default=5, validation_alias="ADMIN_LOGIN_MAX_ATTEMPTS")
    admin_login_ip_max_attempts: int = Field(default=10, validation_alias="ADMIN_LOGIN_IP_MAX_ATTEMPTS")
    admin_login_window_seconds: int = Field(default=300, validation_alias="ADMIN_LOGIN_WINDOW_SECONDS")
    admin_login_lockout_seconds: int = Field(default=900, validation_alias="ADMIN_LOGIN_LOCKOUT_SECONDS")
    admin_session_ttl_hours: int = Field(default=12, validation_alias="ADMIN_SESSION_TTL_HOURS")
    admin_remember_me_ttl_days: int = Field(default=30, validation_alias="ADMIN_REMEMBER_ME_TTL_DAYS")

    enable_openapi: bool = Field(default=True, validation_alias="ENABLE_OPENAPI")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
