import json
import os
from functools import lru_cache
from typing import Literal

import boto3
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_RUNTIME_SECRET_LOADED = False


def _load_runtime_secret_into_environ() -> None:
    """Load AWS Secrets Manager JSON config once, without overwriting explicit env vars."""
    global _RUNTIME_SECRET_LOADED

    if _RUNTIME_SECRET_LOADED:
        return

    _RUNTIME_SECRET_LOADED = True

    secret_name = os.environ.get("AVENTI_RUNTIME_SECRET_NAME")
    if not secret_name:
        return

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_name)
    secret_string = response.get("SecretString")
    if not secret_string:
        return

    payload = json.loads(secret_string)
    if not isinstance(payload, dict):
        raise ValueError("AVENTI_RUNTIME_SECRET_NAME must contain a JSON object")

    for key, value in payload.items():
        if value is None or key in os.environ:
            continue
        os.environ[str(key)] = str(value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    # Accept both full ('development') and short ('dev') forms — Terraform uses
    # short forms for resource naming (aventi-dev-worker); the backend treats
    # them as equivalent.
    env: Literal[
        "dev", "development",
        "test",
        "staging",
        "prod", "production",
    ] = Field(default="development", alias="AVENTI_ENV")
    host: str = Field(default="0.0.0.0", alias="AVENTI_BACKEND_HOST")
    port: int = Field(default=8000, alias="AVENTI_BACKEND_PORT")
    log_level: str = Field(default="INFO", alias="AVENTI_BACKEND_LOG_LEVEL")
    database_url: str | None = Field(default=None, alias="AVENTI_DATABASE_URL")
    supabase_url: str | None = Field(default=None, alias="AVENTI_SUPABASE_URL")
    supabase_jwks_url: str | None = Field(default=None, alias="AVENTI_SUPABASE_JWKS_URL")
    supabase_jwt_audience: str = Field(
        default="authenticated", alias="AVENTI_SUPABASE_JWT_AUDIENCE"
    )
    supabase_jwt_secret: str | None = Field(default=None, alias="AVENTI_SUPABASE_JWT_SECRET")
    supabase_issuer: str | None = Field(default=None, alias="AVENTI_SUPABASE_ISSUER")
    supabase_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AVENTI_SUPABASE_SECRET_KEY",
            "AVENTI_SUPABASE_SERVICE_ROLE_KEY",
        ),
    )
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
    serpapi_api_key: str | None = Field(default=None, alias="SERPAPI_API_KEY")
    pollinations_api_key: str | None = Field(default=None, alias="POLLINATIONS_API_KEY")
    cors_origins: list[str] = ["*"]
    worker_poll_seconds: float = 2.0
    sqs_worker_queue_url: str | None = Field(default=None, alias="SQS_WORKER_QUEUE_URL")
    aws_endpoint_url: str | None = Field(default=None, alias="AWS_ENDPOINT_URL")
    enable_verification: bool = Field(default=True, alias="AVENTI_ENABLE_VERIFICATION")
    seen_events_window_days: int = Field(default=30, alias="AVENTI_SEEN_EVENTS_WINDOW_DAYS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_runtime_secret_into_environ()
    return Settings()
