"""Payment endpoints — implements C3 contract exactly.

POST /api/payments/create  → 200 / 404
POST /api/payments/webhook → 200 / 400
"""

from __future__ import annotations

import structlog
import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import require_api_key
from src.api.schemas import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    WebhookResponse,
)
from src.db.models import Payment, Trip, TripOutput
from src.db.session import get_session
from src.lib.config import settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

# Configure Stripe SDK at module load time — safe because settings are read-only
stripe.api_key = settings.stripe_secret_key


@router.post(
    "/create",
    status_code=status.HTTP_200_OK,
    response_model=CreatePaymentResponse,
    responses={404: {"description": "Trip not found"}},
    dependencies=[Depends(require_api_key)],
)
async def create_payment(
    body: CreatePaymentRequest,
    session: AsyncSession = Depends(get_session),
) -> CreatePaymentResponse:
    """Create a Stripe Checkout session and a pending Payment row."""

    # Verify trip exists
    trip = await session.get(Trip, body.trip_id)
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "trip_not_found"},
        )

    amount_cents = settings.stripe_price_brl_cents

    # Create Stripe Checkout Session
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "brl",
                        "product_data": {
                            "name": f"Luxury Europe Trip — {trip.country} ({trip.days} days)",
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            metadata={"trip_id": body.trip_id},
            # success/cancel URLs should come from env in a real deployment
            success_url="https://t.me/your_bot?start=payment_success",
            cancel_url="https://t.me/your_bot?start=payment_cancel",
        )
    except stripe.StripeError as exc:
        log.error("stripe_checkout_create_failed", trip_id=body.trip_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider unavailable",
        ) from exc

    # Persist pending payment row
    payment = Payment(
        trip_id=body.trip_id,
        provider="stripe",
        amount_cents=amount_cents,
        currency="BRL",
        status="pending",
        external_id=checkout_session.id,
    )
    session.add(payment)
    await session.flush()

    log.info(
        "payment_created",
        payment_id=payment.id,
        trip_id=body.trip_id,
        stripe_session_id=checkout_session.id,
    )

    return CreatePaymentResponse(
        payment_url=checkout_session.url or "",
        payment_id=payment.id,
        amount_brl=amount_cents // 100,
    )


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    response_model=WebhookResponse,
    responses={400: {"description": "Invalid signature"}},
    # No X-API-Key dependency — Stripe signs its own webhooks
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
    session: AsyncSession = Depends(get_session),
) -> WebhookResponse:
    """Handle Stripe webhook events.

    Signature verification uses stripe.Webhook.construct_event with HMAC-SHA256.
    Any verification failure → 400 (never 500).
    """
    payload = await request.body()

    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_signature"},
        )

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=settings.stripe_webhook_secret,
        )
    except stripe.SignatureVerificationError as exc:
        log.warning("stripe_webhook_invalid_signature", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_signature"},
        ) from exc
    except Exception as exc:
        log.error("stripe_webhook_parse_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_signature"},
        ) from exc

    # Handle checkout.session.completed — mark payment as paid
    if event["type"] == "checkout.session.completed":
        checkout_session = event["data"]["object"]
        stripe_session_id: str = checkout_session["id"]
        trip_id: str | None = checkout_session.get("metadata", {}).get("trip_id")

        if trip_id:
            result = await session.execute(
                select(Payment).where(
                    Payment.external_id == stripe_session_id,
                    Payment.trip_id == trip_id,
                )
            )
            payment = result.scalar_one_or_none()

            if payment and payment.status != "paid":
                payment.status = "paid"
                await session.flush()
                log.info(
                    "payment_confirmed",
                    payment_id=payment.id,
                    trip_id=trip_id,
                    stripe_session_id=stripe_session_id,
                )

    return WebhookResponse(received=True)
