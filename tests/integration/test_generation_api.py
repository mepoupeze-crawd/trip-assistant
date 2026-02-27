"""Integration tests for the Generation API (C3, C4 contracts).

Endpoints covered:
  POST /api/trips/:id/generate  — enqueue generation job
  GET  /api/trips/:id/status    — poll generation status
  GET  /api/trips/:id/output    — retrieve document download links

Key contracts:
  POST generate → 202 { trip_id, output_id, status: "queued" } when payment confirmed
  POST generate → 409 { error: payment_not_confirmed } when no paid payment
  POST generate → 404 { error: trip_not_found } for unknown trip_id
  GET status → 200 { trip_id, output_id, status, error_message }
  GET output → 200 { trip_id, pdf_url, docx_url } when status=done
  GET output → 425 { error: output_not_ready, status } when still running
  GET output → 404 { error: output_not_found } for unknown trip_id
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TripOutput


pytestmark = pytest.mark.asyncio


class TestEnqueueGeneration:
    async def test_enqueues_job_after_payment(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        api_headers: dict,
        mocker,
    ):
        """POST /api/trips/:id/generate after confirmed payment → 202, status=queued."""
        # Arrange
        trip, _payment = await confirmed_payment_factory()

        # Mock celery_app.send_task to avoid real Redis connection
        mock_send = mocker.patch("src.api.routers.trips.celery_app.send_task")
        mock_send.return_value = None

        # Act
        response = await client.post(
            f"/api/trips/{trip.id}/generate",
            headers=api_headers,
        )

        # Assert
        assert response.status_code == 202, (
            f"Expected 202, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("trip_id") == trip.id
        assert "output_id" in body
        assert body.get("status") == "queued"
        uuid.UUID(body["output_id"])  # must be valid UUID

    async def test_celery_task_is_enqueued_with_correct_payload(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        api_headers: dict,
        mocker,
    ):
        """Celery task should be called with trip_id and output_id."""
        trip, _payment = await confirmed_payment_factory()

        mock_send = mocker.patch("src.api.routers.trips.celery_app.send_task")
        mock_send.return_value = None

        response = await client.post(
            f"/api/trips/{trip.id}/generate",
            headers=api_headers,
        )
        assert response.status_code == 202

        # Verify celery_app.send_task was called with correct queue and payload
        assert mock_send.called, "celery_app.send_task should have been called"
        call_args = mock_send.call_args
        assert call_args.kwargs.get("queue") == "trip_generation", (
            "Must use queue='trip_generation' per C4 contract"
        )
        assert "trip_id" in str(call_args), "task payload must include trip_id"

    async def test_returns_409_without_payment(
        self,
        client: AsyncClient,
        trip_factory,
        api_headers: dict,
    ):
        """No confirmed payment → 409 payment_not_confirmed."""
        trip = await trip_factory()
        response = await client.post(
            f"/api/trips/{trip.id}/generate",
            headers=api_headers,
        )
        assert response.status_code == 409, (
            f"Expected 409, got {response.status_code}: {response.text}"
        )
        assert response.json().get("detail", {}).get("error") == "payment_not_confirmed"

    async def test_returns_404_for_unknown_trip(
        self, client: AsyncClient, api_headers: dict
    ):
        """Nonexistent trip_id → 404 trip_not_found."""
        fake_id = str(uuid.uuid4())
        response = await client.post(
            f"/api/trips/{fake_id}/generate",
            headers=api_headers,
        )
        assert response.status_code == 404, (
            f"Expected 404 for unknown trip, got {response.status_code}"
        )
        assert response.json().get("detail", {}).get("error") == "trip_not_found"

    async def test_returns_403_without_api_key(
        self, client: AsyncClient, trip_factory
    ):
        trip = await trip_factory()
        response = await client.post(f"/api/trips/{trip.id}/generate")
        assert response.status_code == 403


class TestStatusPolling:
    async def test_returns_queued_status(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        db_session: AsyncSession,
        api_headers: dict,
        mocker,
    ):
        """GET /api/trips/:id/status returns status=queued when job just enqueued."""
        trip, _payment = await confirmed_payment_factory()

        # Manually insert a TripOutput in 'queued' state
        output = TripOutput(trip_id=trip.id, status="queued")
        db_session.add(output)
        await db_session.flush()

        response = await client.get(
            f"/api/trips/{trip.id}/status", headers=api_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "queued"
        assert body.get("trip_id") == trip.id
        assert "output_id" in body

    async def test_returns_done_status_when_complete(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        db_session: AsyncSession,
        api_headers: dict,
    ):
        """GET /api/trips/:id/status returns status=done after worker finishes."""
        trip, _payment = await confirmed_payment_factory()

        output = TripOutput(
            trip_id=trip.id,
            status="done",
            pdf_url=f"https://s3.example.com/trips/{trip.id}/itinerary.pdf",
            docx_url=f"https://s3.example.com/trips/{trip.id}/itinerary.docx",
        )
        db_session.add(output)
        await db_session.flush()

        response = await client.get(
            f"/api/trips/{trip.id}/status", headers=api_headers
        )
        assert response.status_code == 200
        assert response.json().get("status") == "done"

    async def test_returns_failed_with_error_message(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        db_session: AsyncSession,
        api_headers: dict,
    ):
        """GET /api/trips/:id/status returns status=failed with error_message."""
        trip, _payment = await confirmed_payment_factory()

        output = TripOutput(
            trip_id=trip.id,
            status="failed",
            error_message="External API rate limit exceeded",
        )
        db_session.add(output)
        await db_session.flush()

        response = await client.get(
            f"/api/trips/{trip.id}/status", headers=api_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "failed"
        assert body.get("error_message") == "External API rate limit exceeded"

    async def test_status_returns_404_for_unknown_trip(
        self, client: AsyncClient, api_headers: dict
    ):
        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"/api/trips/{fake_id}/status", headers=api_headers
        )
        assert response.status_code == 404


class TestOutputLinks:
    async def test_returns_pdf_and_docx_urls_when_done(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        db_session: AsyncSession,
        api_headers: dict,
    ):
        """GET /api/trips/:id/output → 200 { trip_id, pdf_url, docx_url } when done."""
        trip, _payment = await confirmed_payment_factory()
        pdf_url = f"https://s3.example.com/trips/{trip.id}/itinerary.pdf"
        docx_url = f"https://s3.example.com/trips/{trip.id}/itinerary.docx"

        output = TripOutput(
            trip_id=trip.id,
            status="done",
            pdf_url=pdf_url,
            docx_url=docx_url,
        )
        db_session.add(output)
        await db_session.flush()

        response = await client.get(
            f"/api/trips/{trip.id}/output", headers=api_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("trip_id") == trip.id
        assert body.get("pdf_url") == pdf_url
        assert body.get("docx_url") == docx_url

    async def test_returns_425_when_still_queued(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        db_session: AsyncSession,
        api_headers: dict,
    ):
        """GET /api/trips/:id/output → 425 { error: output_not_ready, status } when queued."""
        trip, _payment = await confirmed_payment_factory()

        output = TripOutput(trip_id=trip.id, status="queued")
        db_session.add(output)
        await db_session.flush()

        response = await client.get(
            f"/api/trips/{trip.id}/output", headers=api_headers
        )
        assert response.status_code == 425, (
            f"Expected 425 for queued output, got {response.status_code}"
        )
        body = response.json().get("detail", {})
        assert body.get("error") == "output_not_ready"
        assert body.get("status") in ("queued", "running")

    async def test_returns_425_when_still_running(
        self,
        client: AsyncClient,
        confirmed_payment_factory,
        db_session: AsyncSession,
        api_headers: dict,
    ):
        """GET /api/trips/:id/output → 425 when status=running."""
        trip, _payment = await confirmed_payment_factory()

        output = TripOutput(trip_id=trip.id, status="running")
        db_session.add(output)
        await db_session.flush()

        response = await client.get(
            f"/api/trips/{trip.id}/output", headers=api_headers
        )
        assert response.status_code == 425
        assert response.json().get("detail", {}).get("error") == "output_not_ready"

    async def test_returns_404_for_unknown_trip(
        self, client: AsyncClient, api_headers: dict
    ):
        """GET /api/trips/:id/output → 404 for nonexistent trip."""
        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"/api/trips/{fake_id}/output", headers=api_headers
        )
        assert response.status_code == 404
        assert response.json().get("detail", {}).get("error") in ("output_not_found", "trip_not_found")

    async def test_output_returns_403_without_api_key(
        self, client: AsyncClient, trip_factory
    ):
        trip = await trip_factory()
        response = await client.get(f"/api/trips/{trip.id}/output")
        assert response.status_code == 403
