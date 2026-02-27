# Infrastructure — Luxury Europe Trip Planner

## Architecture Overview

Three processes share one Docker image, selected via `PROCESS_TYPE` env var:

| PROCESS_TYPE | Command | Port |
|---|---|---|
| `api` | `uvicorn src.api.main:app` | 8000 |
| `bot` | `python -m src.bot.main` | — |
| `worker` | `celery -A src.worker.celery_app worker` | — |
| `migrate` | `alembic upgrade head` | — |

External services: PostgreSQL 16, Redis 7, S3/Cloudflare R2.

---

## Local Development

### Prerequisites
- Docker + Docker Compose
- `.env` file (copy from `.env.example` and fill in real values)

### First run

```sh
# 1. Copy and configure secrets
cp .env.example .env
# Edit .env with real values

# 2. Run database migrations (once, or after schema changes)
docker-compose run --rm migrate

# 3. Start all services
docker-compose up
```

API is available at http://localhost:8000
Health check: http://localhost:8000/health

### Useful commands

```sh
# Rebuild after code changes
docker-compose build

# Start only infrastructure (postgres + redis)
docker-compose up postgres redis

# Run a one-off command inside the app image
docker-compose run --rm api python -c "from src.api.main import app; print('ok')"

# View logs for a specific service
docker-compose logs -f worker
```

---

## Production Deploy

### Supported platforms
Railway, Render, Fly.io, or any Docker-compatible host.

### Steps

1. **Set environment variables** — use the platform's secret management. Never bake secrets into the image or commit them to Git. See `.env.example` for the full list of required variables.

2. **Run migrations before starting app processes:**
   ```sh
   # Railway / Render: configure a "release command" or one-off job
   PROCESS_TYPE=migrate docker run <image> sh -c "alembic upgrade head"
   ```

3. **Deploy the three processes** as separate services (or containers), each with the same image and different `PROCESS_TYPE`:
   - `api` — exposed publicly (behind your platform's reverse proxy)
   - `bot` — internal, no public port needed
   - `worker` — internal, no public port needed

4. **Rollback** — redeploy the previous image tag. No state is stored in the image. Database rollback requires a down-migration (`alembic downgrade -1`) — use with care.

### Required environment variables (production)

See `.env.example` for the full list. Minimum required at runtime:

```
DATABASE_URL
REDIS_URL
INTERNAL_API_KEY   # >= 32 random chars
TELEGRAM_BOT_TOKEN
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_BUCKET_NAME
SENTRY_DSN
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Secrets — never in the image

All secrets are injected at runtime via environment variables.
The Docker image contains NO credentials, tokens, or keys.

---

## Health Check Dependency

The `api` service exposes `GET /health` which returns:

```json
{"status": "ok"}
```

The `docker-compose.yml` healthcheck and the `bot` service `depends_on` condition rely on this endpoint being available.

**Flag for backend agent:** the `GET /health` endpoint must be implemented in `src/api/main.py`. It must return HTTP 200 with `{"status": "ok"}` and must NOT require authentication.

---

## CI/CD Pipeline

See `.github/workflows/ci.yml`:

1. **lint** — ruff + mypy
2. **test** — pytest with ephemeral postgres + redis services
3. **build** — Docker multi-stage build + smoke import tests (needs lint + test to pass)

### Extending for production deploys

Add a `deploy` job after `build` using GitHub Environments for secret protection:

```yaml
deploy:
  needs: [build]
  runs-on: ubuntu-latest
  environment: production   # requires reviewer approval + has prod secrets
  steps:
    - name: Push to registry and trigger redeploy
      # ... platform-specific deploy step
```

---

## Cost Notes

- PostgreSQL + Redis on Railway/Render: ~$10-20/month (managed)
- Cloudflare R2: free tier covers MVP-scale storage + bandwidth
- Sentry: free tier (5k events/month) sufficient for MVP
