from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    env: Literal["development", "test", "staging", "production"] = Field(
        default="development", alias="AVENTI_ENV"
    )
    host: str = Field(default="0.0.0.0", alias="AVENTI_BACKEND_HOST")
    port: int = Field(default=8000, alias="AVENTI_BACKEND_PORT")
    log_level: str = Field(default="INFO", alias="AVENTI_BACKEND_LOG_LEVEL")
    database_url: str | None = Field(default=None, alias="AVENTI_DATABASE_URL")
    supabase_url: str | None = Field(default=None, alias="AVENTI_SUPABASE_URL")
    supabase_jwks_url: str | None = Field(default=None, alias="AVENTI_SUPABASE_JWKS_URL")
    supabase_jwt_audience: str = Field(default="authenticated", alias="AVENTI_SUPABASE_JWT_AUDIENCE")
    supabase_jwt_secret: str | None = Field(default=None, alias="AVENTI_SUPABASE_JWT_SECRET")
    supabase_issuer: str | None = Field(default=None, alias="AVENTI_SUPABASE_ISSUER")
    internal_api_key: str | None = Field(default=None, alias="AVENTI_INTERNAL_API_KEY")
    free_swipe_limit: int = Field(default=10, alias="AVENTI_FREE_SWIPE_LIMIT")
    feed_verification_max_age_hours: int = Field(
        default=72, alias="AVENTI_FEED_VERIFICATION_MAX_AGE_HOURS"
    )
    feed_unverified_grace_hours: int = Field(
        default=48, alias="AVENTI_FEED_UNVERIFIED_GRACE_HOURS"
    )
    auth_dev_bypass: bool = Field(default=True, alias="AVENTI_AUTH_DEV_BYPASS")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    cors_origins: list[str] = ["*"]
    worker_poll_seconds: float = 2.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
