"""Celery tasks — trip generation pipeline.

Task: worker.tasks.generate_trip
Queue: trip_generation (C4 contract)
Retries: 3, backoff 1s / 5s / 30s (C4 contract)

Pipeline:
  1. Load trip from DB
  2. Build stub recommendations (real scraping/API layer TBD — pluggable)
  3. Apply rules engine filtering
  4. Compose itinerary (city/day distribution, daily schedule)
  5. Generate PDF + DOCX
  6. Upload to S3/R2
  7. Update trip_outputs row with URLs and status "done"
  8. On any error: update status "failed" + error_message, then re-raise for retry
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from src.worker.celery_app import celery_app
from src.worker.doc_generator import generate_docx, generate_pdf
from src.worker.rules_engine import (
    RecommendationCandidate,
    check_budget_feasibility,
    filter_recommendations,
)
from src.worker.storage import upload_and_sign
from src.worker.trip_composer import compose

log = structlog.get_logger(__name__)

# Retry countdown schedule — 1s, 5s, 30s (C4 contract)
RETRY_COUNTDOWNS = [1, 5, 30]


def _get_retry_countdown(attempt: int) -> int:
    """Return countdown seconds for the given retry attempt (0-indexed)."""
    idx = min(attempt, len(RETRY_COUNTDOWNS) - 1)
    return RETRY_COUNTDOWNS[idx]


def _build_stub_recommendations(
    trip_data: dict[str, Any],
) -> list[RecommendationCandidate]:
    """Build placeholder recommendations for the trip.

    In production, this would call a data layer (Google Maps API, TripAdvisor,
    web scraper, etc.). For the MVP, stubs are used so the pipeline is end-to-end
    runnable without external API keys.

    Stubs pass quality thresholds so the rules engine lets them through.
    """
    country: str = trip_data.get("country", "Italy")
    cities: list[str] = trip_data.get("cities", [country])

    candidates: list[RecommendationCandidate] = []

    for city in cities:
        # Hotels — threshold: 4.0 rating, 100 reviews
        for i in range(12):
            candidates.append(
                RecommendationCandidate(
                    city=city,
                    type="hotel",
                    name=f"{city} Grand Hotel {i+1}",
                    rating=4.1 + (i % 5) * 0.1,
                    review_count=120 + i * 20,
                    price_hint="€€€" if i < 5 else "€€",
                    source_name="TripAdvisor",
                    source_url=f"https://tripadvisor.com/hotels/{city.lower().replace(' ', '-')}-{i+1}",
                )
            )

        # Attractions — threshold: 4.0 rating, 500 reviews
        for i in range(12):
            candidates.append(
                RecommendationCandidate(
                    city=city,
                    type="attraction",
                    name=f"{city} Museum {i+1}",
                    rating=4.2 + (i % 4) * 0.1,
                    review_count=600 + i * 100,
                    price_hint=None,
                    source_name="Google Maps",
                    source_url=f"https://maps.google.com/?q={city.replace(' ', '+')}+museum+{i+1}",
                )
            )

        # Activities — threshold: 4.0 rating, 500 reviews
        for i in range(12):
            candidates.append(
                RecommendationCandidate(
                    city=city,
                    type="activity",
                    name=f"{city} Walking Tour {i+1}",
                    rating=4.3 + (i % 3) * 0.1,
                    review_count=550 + i * 80,
                    price_hint="€" if i < 6 else "€€",
                    source_name="GetYourGuide",
                    source_url=f"https://getyourguide.com/s/{city.lower().replace(' ', '-')}-tour-{i+1}",
                )
            )

        # Restaurants — threshold: 4.2 rating, 200 reviews
        for i in range(12):
            candidates.append(
                RecommendationCandidate(
                    city=city,
                    type="restaurant",
                    name=f"Osteria {city} {i+1}",
                    rating=4.3 + (i % 4) * 0.1,
                    review_count=250 + i * 30,
                    price_hint="€€" if i < 6 else "€€€",
                    source_name="Google Maps",
                    source_url=f"https://maps.google.com/?q={city.replace(' ', '+')}+restaurant+{i+1}",
                )
            )

        # Bars — threshold: 4.2 rating, 200 reviews
        for i in range(12):
            candidates.append(
                RecommendationCandidate(
                    city=city,
                    type="bar",
                    name=f"Bar {city} {i+1}",
                    rating=4.3 + (i % 3) * 0.1,
                    review_count=210 + i * 25,
                    price_hint="€",
                    source_name="Google Maps",
                    source_url=f"https://maps.google.com/?q={city.replace(' ', '+')}+bar+{i+1}",
                )
            )

    return candidates


async def _run_generation(trip_id: str, output_id: str) -> tuple[str, str]:
    """Core async generation logic — returns (pdf_url, docx_url).

    Separated from the Celery task so it can be unit-tested without
    Celery infrastructure.
    """
    from src.db.models import Recommendation, Trip, TripOutput
    from src.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        # ── 1. Load trip ──────────────────────────────────────────────────────
        trip = await session.get(Trip, trip_id)
        if trip is None:
            raise ValueError(f"Trip {trip_id} not found in database")

        output = await session.get(TripOutput, output_id)
        if output is None:
            raise ValueError(f"TripOutput {output_id} not found in database")

        # Mark as running
        output.status = "running"
        await session.commit()

        log.info("generation_started", trip_id=trip_id, output_id=output_id)

        preferences: dict[str, Any] = trip.preferences_json
        country: str = trip.country
        days: int = trip.days

        # ── 2. Build candidates ───────────────────────────────────────────────
        # Select cities upfront so stubs are city-specific
        from src.worker.trip_composer import select_cities
        city_slots = select_cities(country, days, preferences)
        cities = [slot.city for slot in city_slots]

        trip_data: dict[str, Any] = {
            "country": country,
            "cities": cities,
            "days": days,
            "party_size": trip.party_size,
            "preferences": preferences,
        }

        candidates = _build_stub_recommendations(trip_data)

        # ── 3. Apply rules engine ─────────────────────────────────────────────
        all_types = ["hotel", "attraction", "activity", "restaurant", "bar"]
        passing_candidates: list[RecommendationCandidate] = []

        for city in cities:
            for rec_type in all_types:
                city_type_candidates = [
                    c for c in candidates
                    if c.city == city and c.type == rec_type
                ]
                result = filter_recommendations(city_type_candidates, rec_type, city)
                passing_candidates.extend(result.passing)

        # Budget feasibility check (logged, not blocking for MVP)
        check_budget_feasibility(
            hotel_pref=preferences.get("hotel", "mixed"),
            days=days,
            party_size=trip.party_size,
            budget_per_person_brl=trip.budget_per_person_brl,
        )

        # ── 4. Compose itinerary ──────────────────────────────────────────────
        composed = compose(
            country=country,
            days=days,
            preferences=preferences,
            start_date=None,  # user gave month/year — placeholder dates
            all_recommendations=passing_candidates,
        )

        # ── 5. Persist recommendations ────────────────────────────────────────
        for rec in passing_candidates:
            recommendation = Recommendation(
                trip_id=trip_id,
                city=rec.city,
                type=rec.type,
                name=rec.name,
                rating=rec.rating,
                review_count=rec.review_count,
                price_hint=rec.price_hint,
                source_name=rec.source_name,
                source_url=rec.source_url,
            )
            session.add(recommendation)
        await session.flush()

        # ── 6. Generate documents ─────────────────────────────────────────────
        trip_meta: dict[str, Any] = {
            "country": country,
            "days": days,
            "party_size": trip.party_size,
            "dates_or_month": trip.dates_or_month,
            "origin": trip.origin,
        }

        pdf_bytes = generate_pdf(composed, trip_meta)
        docx_bytes = generate_docx(composed, trip_meta)

        # ── 7. Upload to S3/R2 ────────────────────────────────────────────────
        pdf_url = upload_and_sign(pdf_bytes, trip_id, "pdf")
        docx_url = upload_and_sign(docx_bytes, trip_id, "docx")

        # ── 8. Mark done ──────────────────────────────────────────────────────
        output.status = "done"
        output.pdf_url = pdf_url
        output.docx_url = docx_url
        await session.commit()

        log.info(
            "generation_complete",
            trip_id=trip_id,
            output_id=output_id,
            pdf_url=pdf_url,
        )

        return pdf_url, docx_url


async def _mark_failed(output_id: str, error_message: str) -> None:
    """Mark TripOutput as failed in the database."""
    from src.db.models import TripOutput
    from src.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        output = await session.get(TripOutput, output_id)
        if output:
            output.status = "failed"
            output.error_message = error_message[:1000]  # cap length
            await session.commit()


@celery_app.task(
    name="worker.tasks.generate_trip",
    bind=True,
    max_retries=3,
    queue="trip_generation",
    acks_late=True,  # Only ack after task completes (prevents message loss)
)
def generate_trip(self: Task, trip_id: str, output_id: str) -> dict[str, str]:
    """Celery task: generate trip documents end-to-end.

    C4 contract:
    - Queue: trip_generation
    - Task name: worker.tasks.generate_trip
    - Payload keys: trip_id, output_id
    - Retries: 3, backoff 1s/5s/30s
    """
    log.info(
        "generate_trip_task_started",
        trip_id=trip_id,
        output_id=output_id,
        attempt=self.request.retries,
    )

    try:
        pdf_url, docx_url = asyncio.run(_run_generation(trip_id, output_id))
        return {"trip_id": trip_id, "output_id": output_id, "status": "done"}

    except SoftTimeLimitExceeded as exc:
        error_msg = "Task timed out (soft limit exceeded)"
        log.error("generate_trip_soft_timeout", trip_id=trip_id, output_id=output_id)
        asyncio.run(_mark_failed(output_id, error_msg))
        raise

    except Exception as exc:
        error_msg = str(exc)
        attempt = self.request.retries

        log.error(
            "generate_trip_failed",
            trip_id=trip_id,
            output_id=output_id,
            attempt=attempt,
            error=error_msg,
        )

        if attempt < self.max_retries:
            countdown = _get_retry_countdown(attempt)
            log.info(
                "generate_trip_retry",
                trip_id=trip_id,
                countdown=countdown,
                attempt=attempt + 1,
            )
            raise self.retry(exc=exc, countdown=countdown)
        else:
            # Final failure — mark as failed in DB
            asyncio.run(_mark_failed(output_id, error_msg))
            raise
