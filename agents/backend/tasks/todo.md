# Tasks — Backend Agent — Luxury Europe Trip Planner

## Active

- [x] Create project structure (src/ layout)
- [x] Create pyproject.toml with all dependencies
- [x] Create .env.example
- [x] Create alembic.ini
- [x] Create src/lib/config.py (Pydantic Settings)
- [x] Create src/db/base.py (SQLAlchemy declarative base)
- [x] Create src/db/models.py (User, Trip, TripOutput, Recommendation, Payment)
- [x] Create src/db/session.py (async engine + SessionLocal)
- [x] Create src/db/migrations/ (Alembic env.py + initial migration)
- [x] Create src/api/schemas.py (Pydantic v2 request/response models)
- [x] Create src/api/deps.py (X-API-Key dependency)
- [x] Create src/api/routers/trips.py (POST /api/trips, generate, status, output)
- [x] Create src/api/routers/payments.py (create, webhook)
- [x] Create src/api/main.py (FastAPI app, CORS, Sentry)
- [x] Create src/worker/celery_app.py (Celery config)
- [x] Create src/worker/rules_engine.py (quality thresholds, budget logic)
- [x] Create src/worker/trip_composer.py (city/day distribution, daily schedule)
- [x] Create src/worker/doc_generator.py (PDF + DOCX)
- [x] Create src/worker/storage.py (S3/R2 upload, presigned URLs)
- [x] Create src/worker/tasks.py (generate_trip task)
- [x] Create src/bot/handlers/briefing.py (ConversationHandler)
- [x] Create src/bot/handlers/delivery.py (polling loop + send links)
- [x] Create src/bot/main.py (Application)
- [ ] Run import validation checks

## Completed

## Blocked

<!-- nothing blocked -->
