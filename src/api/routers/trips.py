"""Trip endpoints — implements C3 contract exactly.

POST /api/trips          → 201 / 422
POST /api/trips/{id}/generate → 202 / 404 / 409
GET  /api/trips/{id}/status   → 200
GET  /api/trips/{id}/output   → 200 / 404 / 425
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_api_key
from src.api.schemas import (
    CreateTripRequest,
    CreateTripResponse,
    GenerateTripResponse,
    TripOutputResponse,
    TripStatusResponse,
    ValidationErrorResponse,
)
from src.db.models import Payment, Trip, TripOutput, User
from src.db.session import get_session
from src.worker.celery_app import celery_app

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateTripResponse,
    responses={422: {"model": ValidationErrorResponse}},
    dependencies=[Depends(require_api_key)],
)
async def create_trip(
    body: CreateTripRequest,
    session: AsyncSession = Depends(get_session),
) -> CreateTripResponse:
    """Create or reuse a User and create a Trip row."""

    # Upsert user by telegram_id
    result = await session.execute(
        select(User).where(User.telegram_id == body.telegram_user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=body.telegram_user_id,
            name=body.telegram_name,
        )
        session.add(user)
        await session.flush()  # populate user.id without committing

    trip = Trip(
        user_id=user.id,
        origin=body.origin,
        country=body.country,
        dates_or_month=body.dates_or_month,
        days=body.days,
        party_size=body.party_size,
        budget_per_person_brl=body.budget_per_person_brl,
        preferences_json=body.preferences.model_dump(),
    )
    session.add(trip)
    await session.flush()

    log.info(
        "trip_created",
        trip_id=trip.id,
        user_id=user.id,
        country=body.country,
        days=body.days,
    )

    return CreateTripResponse(trip_id=trip.id)


@router.post(
    "/{trip_id}/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerateTripResponse,
    responses={
        404: {"description": "Trip not found"},
        409: {"description": "Payment not confirmed"},
    },
    dependencies=[Depends(require_api_key)],
)
async def generate_trip(
    trip_id: str,
    session: AsyncSession = Depends(get_session),
) -> GenerateTripResponse:
    """Enqueue trip generation after payment is confirmed."""

    # Check trip exists
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "trip_not_found"},
        )

    # Check payment is confirmed (status == "paid")
    result = await session.execute(
        select(Payment).where(
            Payment.trip_id == trip_id,
            Payment.status == "paid",
        )
    )
    paid_payment = result.scalar_one_or_none()

    if paid_payment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "payment_not_confirmed"},
        )

    # Idempotency: if output already queued/running/done, return existing
    result = await session.execute(
        select(TripOutput).where(TripOutput.trip_id == trip_id)
    )
    existing_output = result.scalar_one_or_none()

    if existing_output is not None:
        log.info(
            "generate_trip_idempotent",
            trip_id=trip_id,
            output_id=existing_output.id,
            status=existing_output.status,
        )
        return GenerateTripResponse(
            trip_id=trip_id,
            output_id=existing_output.id,
            status="queued",  # always "queued" in 202 per contract
        )

    # Create output row with status "queued"
    output = TripOutput(trip_id=trip_id, status="queued")
    session.add(output)
    await session.flush()

    # Enqueue Celery task — C4 contract
    celery_app.send_task(
        "worker.tasks.generate_trip",
        kwargs={"trip_id": trip_id, "output_id": output.id},
        queue="trip_generation",
    )

    log.info("trip_generation_queued", trip_id=trip_id, output_id=output.id)

    return GenerateTripResponse(
        trip_id=trip_id,
        output_id=output.id,
        status="queued",
    )


@router.get(
    "/{trip_id}/status",
    status_code=status.HTTP_200_OK,
    response_model=TripStatusResponse,
    dependencies=[Depends(require_api_key)],
)
async def get_trip_status(
    trip_id: str,
    session: AsyncSession = Depends(get_session),
) -> TripStatusResponse:
    """Poll generation status."""

    result = await session.execute(
        select(TripOutput).where(TripOutput.trip_id == trip_id)
    )
    output = result.scalar_one_or_none()

    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "output_not_found"},
        )

    return TripStatusResponse(
        trip_id=trip_id,
        output_id=output.id,
        status=output.status,  # type: ignore[arg-type]
        error_message=output.error_message,
    )


@router.get(
    "/{trip_id}/output",
    status_code=status.HTTP_200_OK,
    response_model=TripOutputResponse,
    responses={
        404: {"description": "Output not found"},
        425: {"description": "Output not ready"},
    },
    dependencies=[Depends(require_api_key)],
)
async def get_trip_output(
    trip_id: str,
    session: AsyncSession = Depends(get_session),
) -> TripOutputResponse:
    """Return presigned URLs when generation is done."""

    result = await session.execute(
        select(TripOutput).where(TripOutput.trip_id == trip_id)
    )
    output = result.scalar_one_or_none()

    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "output_not_found"},
        )

    if output.status in ("queued", "running"):
        raise HTTPException(
            status_code=425,  # Too Early
            detail={"error": "output_not_ready", "status": output.status},
        )

    if output.status == "failed" or not output.pdf_url or not output.docx_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "output_not_found"},
        )

    return TripOutputResponse(
        trip_id=trip_id,
        pdf_url=output.pdf_url,
        docx_url=output.docx_url,
    )
