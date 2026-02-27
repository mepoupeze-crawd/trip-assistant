"""Parametrized auth enforcement tests — C7 contract.

All protected endpoints must return 403 on missing or invalid X-API-Key.
POST /api/payments/webhook is NOT in this list (uses Stripe-Signature instead).
"""
import pytest
from httpx import AsyncClient

PROTECTED_ENDPOINTS = [
    ("POST", "/api/trips", {
        "telegram_user_id": 111,
        "telegram_name": "Test",
        "origin": "GRU",
        "country": "Italy",
        "dates_or_month": "09/2026",
        "days": 7,
        "party_size": "couple",
        "budget_per_person_brl": 20000,
        "preferences": {
            "pace": "medium",
            "focus": ["food", "culture"],
            "crowds": "medium",
            "hotel": "mixed",
            "restrictions": []
        }
    }),
    ("POST", "/api/payments/create", {"trip_id": "00000000-0000-0000-0000-000000000001"}),
    ("POST", "/api/trips/00000000-0000-0000-0000-000000000001/generate", {}),
    ("GET", "/api/trips/00000000-0000-0000-0000-000000000001/status", None),
    ("GET", "/api/trips/00000000-0000-0000-0000-000000000001/output", None),
]


class TestApiKeyEnforcement:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,url,body", PROTECTED_ENDPOINTS)
    async def test_returns_403_without_api_key(self, client: AsyncClient, method, url, body):
        """Missing X-API-Key → 403."""
        if method == "GET":
            response = await client.get(url)
        else:
            response = await client.post(url, json=body)
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,url,body", PROTECTED_ENDPOINTS)
    async def test_returns_403_with_wrong_api_key(self, client: AsyncClient, method, url, body):
        """Wrong X-API-Key → 403."""
        headers = {"X-API-Key": "wrong-key-definitely-invalid"}
        if method == "GET":
            response = await client.get(url, headers=headers)
        else:
            response = await client.post(url, json=body, headers=headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_webhook_does_not_require_api_key(self, client: AsyncClient):
        """POST /api/payments/webhook does NOT use X-API-Key — uses Stripe-Signature."""
        # Without X-API-Key and without Stripe-Signature → 400 (bad sig), not 403
        response = await client.post(
            "/api/payments/webhook",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        # Should get 400 (invalid_signature) not 403 (api key)
        assert response.status_code == 400
        data = response.json()
        assert data.get("detail", {}).get("error") == "invalid_signature"
