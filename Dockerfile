# ─────────────────────────────────────────────
# Stage 1: builder — install deps, compile wheels
# ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for compiling Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest first (cache-friendly)
COPY pyproject.toml .

# Build wheels for all dependencies
RUN pip install --upgrade pip wheel && \
    pip wheel --no-cache-dir --wheel-dir /wheels ".[dev]"

# ─────────────────────────────────────────────
# Stage 2: runtime — minimal image, non-root user
# ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system deps only (libpq for asyncpg, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Install wheels built in builder stage
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* && \
    rm -rf /wheels

# Copy application source
COPY src/ ./src/
COPY alembic.ini ./alembic.ini

# Switch to non-root
USER appuser

# PROCESS_TYPE controls which process runs:
#   api      — uvicorn HTTP server
#   bot      — Telegram bot (long-polling)
#   worker   — Celery worker
#   migrate  — Alembic migrations (run once, restart: no)
ENV PROCESS_TYPE=api

# Expose API port (only used when PROCESS_TYPE=api)
EXPOSE 8000

# Entrypoint delegates to PROCESS_TYPE
CMD ["sh", "-c", "\
  if [ \"$PROCESS_TYPE\" = \"api\" ]; then \
    exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000; \
  elif [ \"$PROCESS_TYPE\" = \"bot\" ]; then \
    exec python -m src.bot.main; \
  elif [ \"$PROCESS_TYPE\" = \"worker\" ]; then \
    exec celery -A src.worker.celery_app worker --loglevel=info -Q trip_generation; \
  elif [ \"$PROCESS_TYPE\" = \"migrate\" ]; then \
    exec alembic upgrade head; \
  else \
    echo \"Unknown PROCESS_TYPE: $PROCESS_TYPE\" && exit 1; \
  fi"]
