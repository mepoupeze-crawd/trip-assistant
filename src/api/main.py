"""FastAPI application entrypoint.

Includes:
- Sentry integration (initialized at startup)
- Structured logging with structlog
- CORS middleware
- All routers mounted
- Health check endpoint
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.lib.config import settings

# ── Sentry (initialize before anything else) ──────────────────────────────────
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

# ── Structured logging ────────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Luxury Europe Trip Planner API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — restrict to internal origins only (bot makes server-side calls)
# Adjust allow_origins for any web dashboard deployed later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this when a web frontend is added
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from src.api.routers import payments, trips  # noqa: E402 — after app init

app.include_router(trips.router)
app.include_router(payments.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Startup / shutdown events ─────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup() -> None:
    log.info("api_starting", sentry_enabled=bool(settings.sentry_dsn))


@app.on_event("shutdown")
async def on_shutdown() -> None:
    log.info("api_shutting_down")
