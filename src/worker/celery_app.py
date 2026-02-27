"""Celery application configuration.

Queue: trip_generation (C4 contract)
Broker + backend: Redis
Retry policy: 3 retries, backoff 1s / 5s / 30s (C4 contract)
"""

from __future__ import annotations

from celery import Celery

from src.lib.config import settings

celery_app = Celery(
    "trip_planner",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.worker.tasks"],
)

celery_app.conf.update(
    # ── Serialization ─────────────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # ── Queues ────────────────────────────────────────────────────────────────
    task_default_queue="trip_generation",
    task_queues={
        "trip_generation": {
            "exchange": "trip_generation",
            "routing_key": "trip_generation",
        },
    },
    # ── Timeouts ──────────────────────────────────────────────────────────────
    task_soft_time_limit=300,   # 5 min — task receives SoftTimeLimitExceeded
    task_time_limit=360,        # 6 min — hard kill
    # ── Retry policy (C4: 3 retries, backoff 1s/5s/30s) ─────────────────────
    task_max_retries=3,
    # ── Result expiry ─────────────────────────────────────────────────────────
    result_expires=86400,  # 24h
    # ── Observability ─────────────────────────────────────────────────────────
    worker_send_task_events=True,
    task_send_sent_event=True,
    # ── Timezone ──────────────────────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,
)
