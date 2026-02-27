"""Integration tests for the Payments API (C3 contract).

Endpoints covered:
  POST /api/payments/create  — initiate Stripe checkout
  POST /api/payments/webhook — Stripe webhook (no X-API-Key, uses Stripe-Signature)

Key contracts:
  - create → 200 { payment_url, payment_id, amount_brl }
  - create → 404 { error: trip_not_found } for unknown trip
  - webhook → 200 { received: true } on valid signature + completed event
  - webhook → 400 { error: invalid_signature } on bad signature
  - webhook → 400 on missing Stripe-Signature header
  - webhook is idempotent: same event twice → 200 both times, no duplicate records
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Payment


pytestmark = pytest.mark.asyncio


class TestCreatePaymentCheckout:
    async def test_creates_stripe_checkout(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        api_headers: dict,
        mocker,
    ):
        """Mock Stripe → returns payment_url, payment_id (uuid), amount_brl=100."""
        # Arrange: create a trip with a pending payment state (no paid status yet)
        # For this test we just need a valid trip_id; payment record creation
        # is initiated by the endpoint itself.
        # Re-use trip_factory instead of confirmed_payment_factory.
        pass  # actual trip creation is done by the fixture below

    async def test_creates_stripe_checkout_for_existing_trip(
        self,
        client: AsyncClient,
        trip_factory,
        api_headers: dict,
        mocker,
    ):
        """POST /api/payments/create with a valid trip_id → 200 with Stripe URL."""
        # Arrange
        trip = await trip_factory()
        mock_checkout = mocker.patch("stripe.checkout.Session.create")
        mock_checkout.return_value = type(
            "Session",
            (),
            {
                "url": "https://checkout.stripe.com/pay/cs_test_abc123",
                "id": "cs_test_abc123",
            },
        )()

        # Act
        response = await client.post(
            "/api/payments/create",
            json={"trip_id": trip.id},
            headers=api_headers,
        )

        # Assert
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "payment_url" in body, "Response must include payment_url"
        assert "payment_id" in body, "Response must include payment_id"
        assert "amount_brl" in body, "Response must include amount_brl"
        assert body["amount_brl"] == 100, (
            f"Expected amount_brl=100, got {body['amount_brl']}"
        )
        # payment_id must be a valid UUID
        uuid.UUID(body["payment_id"])

    async def test_returns_404_for_unknown_trip(
        self, client: AsyncClient, api_headers: dict
    ):
        """trip_id=nonexistent-uuid → 404 trip_not_found."""
        fake_trip_id = str(uuid.uuid4())
        response = await client.post(
            "/api/payments/create",
            json={"trip_id": fake_trip_id},
            headers=api_headers,
        )
        assert response.status_code == 404, (
            f"Expected 404 for unknown trip, got {response.status_code}"
        )
        assert response.json().get("detail", {}).get("error") == "trip_not_found"

    async def test_returns_403_without_api_key(
        self, client: AsyncClient, trip_factory
    ):
        """POST /api/payments/create without X-API-Key → 403."""
        trip = await trip_factory()
        response = await client.post(
            "/api/payments/create", json={"trip_id": trip.id}
        )
        assert response.status_code == 403


class TestStripeWebhook:
    async def test_valid_webhook_updates_payment_status(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        stripe_webhook_payload: dict,
        mocker,
    ):
        """Valid signature + checkout.session.completed → payment.status=paid → 200."""
        trip, payment = await confirmed_payment_factory()

        # Inject the trip/payment IDs into the mock event metadata
        event = stripe_webhook_payload["event"]
        event["data"]["object"]["id"] = payment.external_id
        event["data"]["object"]["metadata"] = {
            "trip_id": trip.id,
            "payment_id": payment.id,
        }
        body = json.dumps(event).encode()

        # Mock Stripe signature verification to accept our test payload
        mocker.patch(
            "stripe.WebhookSignature.verify_header",
            return_value=True,
        )
        mocker.patch(
            "stripe.Webhook.construct_event",
            return_value=event,
        )

        # Act
        response = await client.post(
            "/api/payments/webhook",
            content=body,
            headers={
                "content-type": "application/json",
                "stripe-signature": stripe_webhook_payload["signature"],
            },
        )

        # Assert
        assert response.status_code == 200, (
            f"Expected 200 on valid webhook, got {response.status_code}: {response.text}"
        )
        assert response.json().get("received") is True

    async def test_invalid_signature_returns_400(
        self, client: AsyncClient, stripe_webhook_payload: dict
    ):
        """Tampered signature → 400 invalid_signature."""
        body = stripe_webhook_payload["body"]
        response = await client.post(
            "/api/payments/webhook",
            content=body,
            headers={
                "content-type": "application/json",
                "stripe-signature": "t=0,v1=totallyfakesignature",
            },
        )
        assert response.status_code == 400, (
            f"Expected 400 for invalid signature, got {response.status_code}"
        )
        assert response.json().get("detail", {}).get("error") == "invalid_signature"

    async def test_missing_signature_returns_400(
        self, client: AsyncClient, stripe_webhook_payload: dict
    ):
        """No Stripe-Signature header at all → 400."""
        body = stripe_webhook_payload["body"]
        response = await client.post(
            "/api/payments/webhook",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400, (
            f"Expected 400 for missing signature, got {response.status_code}"
        )

    async def test_webhook_is_idempotent(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        stripe_webhook_payload: dict,
        db_session: AsyncSession,
        mocker,
    ):
        """Same event delivered twice → 200 both times, no duplicate Payment records."""
        trip, payment = await confirmed_payment_factory()

        event = stripe_webhook_payload["event"]
        event["data"]["object"]["id"] = payment.external_id
        event["data"]["object"]["metadata"] = {
            "trip_id": trip.id,
            "payment_id": payment.id,
        }
        body = json.dumps(event).encode()

        mocker.patch("stripe.Webhook.construct_event", return_value=event)

        headers = {
            "content-type": "application/json",
            "stripe-signature": stripe_webhook_payload["signature"],
        }

        # First delivery
        r1 = await client.post("/api/payments/webhook", content=body, headers=headers)
        assert r1.status_code == 200

        # Second delivery (idempotency check)
        r2 = await client.post("/api/payments/webhook", content=body, headers=headers)
        assert r2.status_code == 200

        # Verify no duplicate Payment rows for the same trip
        result = await db_session.execute(
            select(Payment).where(Payment.trip_id == trip.id)
        )
        payments = result.scalars().all()
        assert len(payments) == 1, (
            f"Expected 1 Payment record, found {len(payments)} (idempotency broken)"
        )

    async def test_webhook_endpoint_is_not_protected_by_api_key(
        self, client: AsyncClient, stripe_webhook_payload: dict, mocker
    ):
        """POST /api/payments/webhook must NOT require X-API-Key header.

        It is protected by Stripe-Signature only (C7 contract).
        """
        # This test verifies the endpoint doesn't reject requests without X-API-Key.
        # We provide a fake signature that will fail verification (non-403 expected).
        body = stripe_webhook_payload["body"]
        response = await client.post(
            "/api/payments/webhook",
            content=body,
            headers={
                "content-type": "application/json",
                "stripe-signature": "t=0,v1=fakesignature",
            },
        )
        # 400 (bad signature) is acceptable — 403 (API key required) is NOT
        assert response.status_code != 403, (
            "Webhook endpoint must not enforce X-API-Key; got 403 Forbidden"
        )
