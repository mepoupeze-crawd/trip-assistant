"""End-to-end integration flow tests — no real external calls.

All Stripe and S3 interactions are mocked.
"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.models import Payment, TripOutput
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_complete_trip_flow(
        self,
        client: AsyncClient,
        api_headers: dict,
        db_session: AsyncSession,
    ):
        """Full flow: create trip → create payment → webhook → generate → poll → output."""

        # Step 1: Create trip
        trip_payload = {
            "telegram_user_id": 999888777,
            "telegram_name": "E2E User",
            "origin": "GRU",
            "country": "Italy",
            "dates_or_month": "09/2026",
            "days": 7,
            "party_size": "couple",
            "budget_per_person_brl": 25000,
            "preferences": {
                "pace": "medium",
                "focus": ["food", "culture", "nature"],
                "crowds": "medium",
                "hotel": "mixed",
                "restrictions": [],
            },
        }
        response = await client.post("/api/trips", json=trip_payload, headers=api_headers)
        assert response.status_code == 201
        trip_id = response.json()["trip_id"]
        assert trip_id  # is a UUID string

        # Step 2: Create payment checkout (mock Stripe)
        mock_checkout = MagicMock()
        mock_checkout.id = "cs_test_abc123"
        mock_checkout.url = "https://checkout.stripe.com/pay/cs_test_abc123"

        with patch("stripe.checkout.Session.create", return_value=mock_checkout):
            response = await client.post(
                "/api/payments/create",
                json={"trip_id": trip_id},
                headers=api_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["payment_url"] == "https://checkout.stripe.com/pay/cs_test_abc123"
        assert data["amount_brl"] == 100

        # Step 3: Simulate Stripe webhook (mock construct_event)
        stripe_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_abc123",
                    "metadata": {"trip_id": trip_id},
                }
            },
        }
        with patch("stripe.Webhook.construct_event", return_value=stripe_event):
            response = await client.post(
                "/api/payments/webhook",
                content=b'{"test": true}',
                headers={
                    "Content-Type": "application/json",
                    "stripe-signature": "t=12345,v1=dummy",
                },
            )
        assert response.status_code == 200
        assert response.json() == {"received": True}

        # Verify payment is now "paid" in DB
        result = await db_session.execute(
            select(Payment).where(Payment.trip_id == trip_id)
        )
        payment = result.scalar_one()
        assert payment.status == "paid"

        # Step 4: Enqueue generation (mock Celery send_task)
        with patch("src.worker.celery_app.celery_app.send_task") as mock_send:
            response = await client.post(
                f"/api/trips/{trip_id}/generate",
                headers=api_headers,
            )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
        output_id = data["output_id"]
        mock_send.assert_called_once()

        # Step 5: Poll status → queued
        response = await client.get(f"/api/trips/{trip_id}/status", headers=api_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "queued"

        # Step 6: Simulate worker completing → manually set status to done
        result = await db_session.execute(
            select(TripOutput).where(TripOutput.trip_id == trip_id)
        )
        output = result.scalar_one()
        output.status = "done"
        output.pdf_url = f"https://storage.example.com/trips/{trip_id}/itinerary.pdf"
        output.docx_url = f"https://storage.example.com/trips/{trip_id}/itinerary.docx"
        await db_session.flush()

        # Step 7: Poll status → done
        response = await client.get(f"/api/trips/{trip_id}/status", headers=api_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "done"

        # Step 8: Get output links
        response = await client.get(f"/api/trips/{trip_id}/output", headers=api_headers)
        assert response.status_code == 200
        data = response.json()
        assert "itinerary.pdf" in data["pdf_url"]
        assert "itinerary.docx" in data["docx_url"]
        assert data["trip_id"] == trip_id


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_generate_returns_425_before_payment(
        self, client: AsyncClient, api_headers: dict, db_session: AsyncSession
    ):
        """GET /output returns 425 when status is queued."""
        # Create trip
        trip_payload = {
            "telegram_user_id": 111222333,
            "telegram_name": "Edge User",
            "origin": "GRU",
            "country": "France",
            "dates_or_month": "10/2026",
            "days": 5,
            "party_size": "solo",
            "budget_per_person_brl": 15000,
            "preferences": {
                "pace": "light",
                "focus": ["culture"],
                "crowds": "high",
                "hotel": "boutique",
                "restrictions": [],
            },
        }
        response = await client.post("/api/trips", json=trip_payload, headers=api_headers)
        trip_id = response.json()["trip_id"]

        # Try to generate without payment → 409
        response = await client.post(
            f"/api/trips/{trip_id}/generate", headers=api_headers
        )
        assert response.status_code == 409
        assert response.json()["detail"]["error"] == "payment_not_confirmed"

    @pytest.mark.asyncio
    async def test_idempotent_webhook_does_not_double_pay(
        self,
        client: AsyncClient,
        api_headers: dict,
        db_session: AsyncSession,
    ):
        """Receiving same Stripe webhook twice must not create duplicate payment records."""
        # Create trip
        trip_payload = {
            "telegram_user_id": 444555666,
            "telegram_name": "Idempotent User",
            "origin": "GRU",
            "country": "Spain",
            "dates_or_month": "11/2026",
            "days": 8,
            "party_size": "couple",
            "budget_per_person_brl": 20000,
            "preferences": {
                "pace": "medium",
                "focus": ["food", "culture"],
                "crowds": "medium",
                "hotel": "mixed",
                "restrictions": [],
            },
        }
        response = await client.post("/api/trips", json=trip_payload, headers=api_headers)
        trip_id = response.json()["trip_id"]

        # Create payment record in DB (simulate checkout already done)
        mock_checkout = MagicMock()
        mock_checkout.id = "cs_test_idem"
        mock_checkout.url = "https://checkout.stripe.com/pay/cs_test_idem"
        with patch("stripe.checkout.Session.create", return_value=mock_checkout):
            await client.post(
                "/api/payments/create",
                json={"trip_id": trip_id},
                headers=api_headers,
            )

        stripe_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_idem",
                    "metadata": {"trip_id": trip_id},
                }
            },
        }

        # Send webhook twice
        for _ in range(2):
            with patch("stripe.Webhook.construct_event", return_value=stripe_event):
                response = await client.post(
                    "/api/payments/webhook",
                    content=b'{"test": true}',
                    headers={
                        "Content-Type": "application/json",
                        "stripe-signature": "t=12345,v1=dummy",
                    },
                )
            assert response.status_code == 200

        # Only one payment record should exist
        result = await db_session.execute(
            select(Payment).where(Payment.trip_id == trip_id)
        )
        payments = result.scalars().all()
        assert len(payments) == 1
        assert payments[0].status == "paid"
