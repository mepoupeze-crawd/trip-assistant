"""ORM models — exactly mirrors the C1 schema contract.

All UUIDs are server-generated (gen_random_uuid() on Postgres side).
JSONB columns use SQLAlchemy's JSON type which maps to JSONB on Postgres.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


def _uuid() -> str:
    """Default factory for UUID primary keys (Python-side fallback)."""
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
        server_default=text("gen_random_uuid()"),
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trips: Mapped[list["Trip"]] = relationship(back_populates="user")


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(Text, nullable=False)
    dates_or_month: Mapped[str] = mapped_column(Text, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    party_size: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # "solo" | "couple"
    budget_per_person_brl: Mapped[int] = mapped_column(Integer, nullable=False)
    preferences_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="trips")
    output: Mapped["TripOutput | None"] = relationship(
        back_populates="trip", uselist=False
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="trip"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="trip")


class TripOutput(Base):
    __tablename__ = "trip_outputs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
        server_default=text("gen_random_uuid()"),
    )
    trip_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("trips.id"), unique=True, nullable=False
    )
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    docx_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    trip: Mapped["Trip"] = relationship(back_populates="output")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
        server_default=text("gen_random_uuid()"),
    )
    trip_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("trips.id"), nullable=False
    )
    city: Mapped[str] = mapped_column(Text, nullable=False)
    # hotel | attraction | activity | restaurant | bar
    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trip: Mapped["Trip"] = relationship(back_populates="recommendations")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
        server_default=text("gen_random_uuid()"),
    )
    trip_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("trips.id"), nullable=False
    )
    # "stripe" | "mercadopago"
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="BRL")
    # pending | paid | failed | refunded
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trip: Mapped["Trip"] = relationship(back_populates="payments")
