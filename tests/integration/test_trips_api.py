"""Integration tests for POST /api/trips (C3 contract).

All cases:
  - Valid request → 201 with trip_id UUID
  - days out of range → 422
  - country not in Europe → 422
  - missing X-API-Key → 403
  - wrong X-API-Key → 403
  - new telegram_id → user created in DB
  - same telegram_id twice → reuses existing user record
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Trip, User


pytestmark = pytest.mark.asyncio


VALID_BODY = {
    "telegram_user_id": 111222333,
    "telegram_name": "Integration Tester",
    "origin": "GRU",
    "country": "Italy",
    "dates_or_month": "09/2026",
    "days": 10,
    "party_size": "couple",
    "budget_per_person_brl": 30000,
    "preferences": {
        "pace": "medium",
        "focus": ["food", "culture", "nature"],
        "crowds": "high",
        "hotel": "mixed",
        "restrictions": [],
    },
}


class TestCreateTrip:
    async def test_creates_trip_successfully(
        self, client: AsyncClient, api_headers: dict
    ):
        """POST with valid full briefing → 201 with trip_id UUID."""
        # Act
        response = await client.post("/api/trips", json=VALID_BODY, headers=api_headers)
        # Assert
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "trip_id" in body, "Response must include trip_id"
        # Must be a valid UUID
        uuid.UUID(body["trip_id"])

    async def test_returns_422_when_days_out_of_range(
        self, client: AsyncClient, api_headers: dict
    ):
        """days=50 is outside valid range → 422 validation_error."""
        body = {**VALID_BODY, "days": 50}
        response = await client.post("/api/trips", json=body, headers=api_headers)
        assert response.status_code == 422, (
            f"Expected 422 for days=50, got {response.status_code}"
        )
        data = response.json()
        assert data.get("error") == "validation_error" or "detail" in data

    async def test_returns_422_when_days_is_zero(
        self, client: AsyncClient, api_headers: dict
    ):
        """days=0 → 422."""
        body = {**VALID_BODY, "days": 0}
        response = await client.post("/api/trips", json=body, headers=api_headers)
        assert response.status_code == 422

    async def test_returns_422_when_country_not_europe(
        self, client: AsyncClient, api_headers: dict
    ):
        """country='Brazil' is outside Europe → 422."""
        body = {**VALID_BODY, "country": "Brazil"}
        response = await client.post("/api/trips", json=body, headers=api_headers)
        assert response.status_code == 422, (
            f"Expected 422 for non-European country, got {response.status_code}"
        )
        data = response.json()
        assert data.get("error") == "validation_error" or "detail" in data

    async def test_returns_422_when_party_size_invalid(
        self, client: AsyncClient, api_headers: dict
    ):
        """party_size must be 'solo' or 'couple'."""
        body = {**VALID_BODY, "party_size": "family"}
        response = await client.post("/api/trips", json=body, headers=api_headers)
        assert response.status_code == 422

    async def test_returns_403_without_api_key(self, client: AsyncClient):
        """No X-API-Key header → 403 Forbidden."""
        response = await client.post("/api/trips", json=VALID_BODY)
        assert response.status_code == 403, (
            f"Expected 403 without API key, got {response.status_code}"
        )

    async def test_returns_403_with_wrong_api_key(self, client: AsyncClient):
        """Wrong X-API-Key → 403 Forbidden."""
        response = await client.post(
            "/api/trips",
            json=VALID_BODY,
            headers={"X-API-Key": "totally-wrong-key"},
        )
        assert response.status_code == 403, (
            f"Expected 403 with wrong API key, got {response.status_code}"
        )

    async def test_creates_user_if_telegram_id_new(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict
    ):
        """A new telegram_id should create a user record in the DB."""
        new_telegram_id = 999_001_001
        body = {**VALID_BODY, "telegram_user_id": new_telegram_id}

        response = await client.post("/api/trips", json=body, headers=api_headers)
        assert response.status_code == 201

        # Verify user was created
        result = await db_session.execute(
            select(User).where(User.telegram_id == new_telegram_id)
        )
        user = result.scalar_one_or_none()
        assert user is not None, (
            f"User with telegram_id={new_telegram_id} should have been created"
        )

    async def test_reuses_user_if_telegram_id_exists(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict
    ):
        """Same telegram_id on two requests → same user record (no duplicate)."""
        repeated_telegram_id = 999_002_002
        body = {**VALID_BODY, "telegram_user_id": repeated_telegram_id}

        # First request
        r1 = await client.post("/api/trips", json=body, headers=api_headers)
        assert r1.status_code == 201

        # Second request with same telegram_id
        r2 = await client.post("/api/trips", json=body, headers=api_headers)
        assert r2.status_code == 201

        # Should still be exactly ONE user record
        result = await db_session.execute(
            select(User).where(User.telegram_id == repeated_telegram_id)
        )
        users = result.scalars().all()
        assert len(users) == 1, (
            f"Expected 1 user, found {len(users)} for telegram_id={repeated_telegram_id}"
        )

    async def test_creates_trip_record_in_db(
        self, client: AsyncClient, db_session: AsyncSession, api_headers: dict
    ):
        """Creating a trip should persist a Trip row in the database."""
        body = {**VALID_BODY, "telegram_user_id": 900_900_900}
        response = await client.post("/api/trips", json=body, headers=api_headers)
        assert response.status_code == 201

        trip_id = response.json()["trip_id"]
        result = await db_session.execute(
            select(Trip).where(Trip.id == trip_id)
        )
        trip = result.scalar_one_or_none()
        assert trip is not None, f"Trip {trip_id} should exist in DB"
        assert trip.country == "Italy"
        assert trip.days == 10

    async def test_response_has_uuid_trip_id(
        self, client: AsyncClient, api_headers: dict
    ):
        """trip_id in response must be a valid UUID string."""
        response = await client.post("/api/trips", json=VALID_BODY, headers=api_headers)
        assert response.status_code == 201
        trip_id = response.json().get("trip_id", "")
        try:
            uuid.UUID(trip_id)
        except ValueError:
            pytest.fail(f"trip_id is not a valid UUID: {trip_id!r}")
