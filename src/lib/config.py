"""Application configuration loaded from environment variables.

Uses Pydantic Settings v2 for type-safe, validated config.
All secrets come from env vars — never hardcoded.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://user:pass@localhost:5432/tripplanner",
        description="Async SQLAlchemy URL (asyncpg driver)",
    )

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL used as Celery broker and backend",
    )

    # ── Internal API Auth ─────────────────────────────────────────────────────
    internal_api_key: str = Field(
        default="changeme-secret",
        description="Shared secret for bot→API calls (X-API-Key header)",
    )

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_bot_token: str = Field(
        default="",
        description="BotFather token",
    )

    # ── Stripe ────────────────────────────────────────────────────────────────
    stripe_secret_key: str = Field(
        default="sk_test_placeholder",
        description="Stripe secret key (sk_test_* or sk_live_*)",
    )
    stripe_webhook_secret: str = Field(
        default="whsec_placeholder",
        description="Stripe webhook signing secret for HMAC verification",
    )
    stripe_price_brl_cents: int = Field(
        default=10000,
        description="Fixed price in BRL cents (10000 = R$100)",
    )

    # ── Storage (S3 / Cloudflare R2) ─────────────────────────────────────────
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    aws_bucket_name: str = Field(default="trip-planner-docs")
    aws_endpoint_url: str | None = Field(
        default=None,
        description="Custom S3 endpoint — set for R2 or MinIO, leave None for real AWS",
    )
    presigned_url_ttl_seconds: int = Field(
        default=7 * 24 * 3600,  # 7 days
        description="Presigned URL expiry in seconds",
    )

    # ── Observability ─────────────────────────────────────────────────────────
    sentry_dsn: str | None = Field(default=None)

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    # Base URL the bot uses to call the internal API.
    # Inside docker-compose the service is "api"; override for local dev.
    api_base_url: str = Field(
        default="http://api:8000",
        description="Internal API base URL used by the bot process",
    )

    # ── Recommendation Provider ───────────────────────────────────────────────
    recommendation_provider: Literal["stub", "google_places"] = Field(
        default="stub",
        description="Recommendation data source. 'stub' for dev/tests, 'google_places' for production.",
    )
    google_places_api_key: str | None = Field(
        default=None,
        description="Google Places API key. Required when RECOMMENDATION_PROVIDER=google_places.",
    )


# Singleton — import and reuse everywhere
settings = Settings()
