"""pytest fixtures shared across the entire test suite.

Design principles:
- DB session uses real Postgres from CI env (DATABASE_URL env var).
- FastAPI client uses httpx AsyncClient for async compatibility.
- External boundaries (Stripe, S3) are always mocked — never real calls in tests.
- Fixtures compose: confirmed_payment_factory depends on trip_factory.
- All secrets use test-only sentinel values that never hit real services.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.base import Base
from src.db.models import Payment, Trip, TripOutput, User

# ---------------------------------------------------------------------------
# Configuration — test-only values
# ---------------------------------------------------------------------------

TEST_API_KEY = "test-key-ci"
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://tripuser:trippass@localhost:5432/tripplanner_test",
)
TEST_STRIPE_WEBHOOK_SECRET = "whsec_test_secret_for_ci"

# ---------------------------------------------------------------------------
# Database engine and session
# ---------------------------------------------------------------------------

_test_engine = create_async_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

_TestSessionLocal = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables() -> AsyncGenerator[None, None]:
    """Create all tables once per session; drop them after all tests finish."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async SQLAlchemy session with real Postgres (from CI env).

    Uses a connection-level transaction so that even when endpoint code calls
    session.commit(), the actual DB is never touched — commits become SAVEPOINTs
    and the outer connection rolls back after the test.
    """
    async with _test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


# ---------------------------------------------------------------------------
# FastAPI TestClient (httpx AsyncClient)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTPX client wired to the FastAPI app.

    Overrides the ``get_session`` dependency so every request uses the
    same test session (and therefore the same transaction that will be
    rolled back after the test).
    """
    # Import here to avoid issues when the app module is not yet created.
    # Marked with skip guard so syntax check passes even without full backend.
    try:
        from src.api.main import app  # type: ignore[import]
        from src.db.session import get_session
    except ImportError:
        pytest.skip("src.api.app not yet implemented by backend agent")

    async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session

    # Patch the INTERNAL_API_KEY so auth middleware accepts TEST_API_KEY.
    os.environ.setdefault("INTERNAL_API_KEY", TEST_API_KEY)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def api_headers() -> dict[str, str]:
    """Valid X-API-Key headers for protected endpoints."""
    return {"X-API-Key": TEST_API_KEY}


# ---------------------------------------------------------------------------
# Valid request bodies (reusable across tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_trip_body() -> dict[str, Any]:
    """A fully valid POST /api/trips request body matching C3 contract."""
    return {
        "telegram_user_id": 123456789,
        "telegram_name": "Teste",
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


# ---------------------------------------------------------------------------
# DB factories
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def trip_factory(db_session: AsyncSession):
    """Factory that creates a Trip (and its owning User) in the DB.

    Usage::

        async def test_something(trip_factory):
            trip = await trip_factory()
            trip_with_overrides = await trip_factory(days=5, country="France")
    """

    async def _create(**overrides: Any) -> Trip:
        user = User(
            telegram_id=overrides.pop("telegram_id", 111222333),
            name=overrides.pop("telegram_name", "Test User"),
        )
        db_session.add(user)
        await db_session.flush()

        trip = Trip(
            user_id=user.id,
            origin=overrides.get("origin", "GRU"),
            country=overrides.get("country", "Italy"),
            dates_or_month=overrides.get("dates_or_month", "09/2026"),
            days=overrides.get("days", 10),
            party_size=overrides.get("party_size", "couple"),
            budget_per_person_brl=overrides.get("budget_per_person_brl", 30000),
            preferences_json=overrides.get(
                "preferences_json",
                {
                    "pace": "medium",
                    "focus": ["food", "culture"],
                    "crowds": "high",
                    "hotel": "mixed",
                    "restrictions": [],
                },
            ),
        )
        db_session.add(trip)
        await db_session.flush()
        return trip

    return _create


@pytest_asyncio.fixture
async def confirmed_payment_factory(
    db_session: AsyncSession,
    trip_factory,
):
    """Factory that creates a Trip with a confirmed (paid) Payment.

    Usage::

        async def test_something(confirmed_payment_factory):
            trip, payment = await confirmed_payment_factory()
    """

    async def _create(**overrides: Any) -> tuple[Trip, Payment]:
        trip = await trip_factory(**overrides)

        payment = Payment(
            trip_id=trip.id,
            provider="stripe",
            amount_cents=10000,
            currency="BRL",
            status="paid",
            external_id=f"cs_test_{uuid.uuid4().hex}",
        )
        db_session.add(payment)
        await db_session.flush()
        return trip, payment

    return _create


# ---------------------------------------------------------------------------
# Stripe webhook helpers
# ---------------------------------------------------------------------------


def _stripe_webhook_signature(payload: bytes, secret: str, timestamp: int) -> str:
    """Compute a valid Stripe-Signature header value.

    Replicates Stripe's HMAC-SHA256 signing algorithm so tests can produce
    signatures that pass ``stripe.WebhookSignature.verify_header()``.
    """
    signed_payload = f"{timestamp}.".encode() + payload
    mac = hmac.new(secret.encode(), signed_payload, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


@pytest.fixture
def stripe_webhook_payload() -> dict[str, Any]:
    """A mock ``checkout.session.completed`` Stripe webhook event.

    Returns a dict with ``body`` (bytes), ``signature`` (header value),
    and ``event`` (parsed dict) so tests can use whichever form they need.
    """
    external_checkout_id = f"cs_test_{uuid.uuid4().hex}"
    event: dict[str, Any] = {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": external_checkout_id,
                "payment_status": "paid",
                "metadata": {},  # tests should inject trip/payment IDs here if needed
            }
        },
    }
    body = json.dumps(event).encode()
    timestamp = int(time.time())
    signature = _stripe_webhook_signature(body, TEST_STRIPE_WEBHOOK_SECRET, timestamp)
    return {
        "body": body,
        "signature": signature,
        "event": event,
        "external_id": external_checkout_id,
    }


# ---------------------------------------------------------------------------
# Mock S3 (moto)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_s3():
    """Mock AWS S3 using moto.

    Activates the moto ``mock_aws`` context and creates the test bucket so
    worker code that uploads PDFs/DOCX files finds a valid bucket.
    """
    with mock_aws():
        import boto3

        bucket_name = os.getenv("AWS_BUCKET_NAME", "trip-planner-docs")
        s3 = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
        s3.create_bucket(Bucket=bucket_name)
        yield s3
