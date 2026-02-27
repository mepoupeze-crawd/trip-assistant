"""Pydantic v2 request and response schemas — implements C3 contracts exactly.

Every field name, type, and response shape matches the contract.
Deviations require tech-lead sign-off.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ── C2: preferences_json ─────────────────────────────────────────────────────

Pace = Literal["light", "medium", "intense"]
Crowd = Literal["low", "medium", "high"]
Hotel = Literal["5star", "boutique", "mixed"]
FocusItem = Literal["food", "culture", "nature"]


class PreferencesSchema(BaseModel):
    """Matches C2 exactly."""

    pace: Pace
    focus: list[FocusItem] = Field(min_length=1, max_length=3)
    crowds: Crowd
    hotel: Hotel
    restrictions: list[str] = Field(default_factory=list)


# ── POST /api/trips ───────────────────────────────────────────────────────────

PartySize = Literal["solo", "couple"]


class CreateTripRequest(BaseModel):
    telegram_user_id: int = Field(..., description="Telegram numeric user ID")
    telegram_name: str = Field(..., min_length=1, max_length=256)
    origin: str = Field(..., min_length=1, max_length=256, description="Origin city or airport")
    country: str = Field(..., min_length=1, max_length=128, description="Destination country in Europe")
    dates_or_month: str = Field(..., min_length=1, max_length=64, description="e.g. '09/2026' or '15/09/2026-30/09/2026'")
    days: int = Field(..., ge=3, le=30, description="Trip duration in days")
    party_size: PartySize
    budget_per_person_brl: int = Field(..., ge=1000, description="Budget in BRL per person")
    preferences: PreferencesSchema


class CreateTripResponse(BaseModel):
    trip_id: str


class ValidationErrorResponse(BaseModel):
    error: Literal["validation_error"] = "validation_error"
    details: str


# ── POST /api/payments/create ─────────────────────────────────────────────────

class CreatePaymentRequest(BaseModel):
    trip_id: str


class CreatePaymentResponse(BaseModel):
    payment_url: str
    payment_id: str
    amount_brl: int = Field(..., description="Amount in BRL (not cents)")


class TripNotFoundResponse(BaseModel):
    error: Literal["trip_not_found"] = "trip_not_found"


# ── POST /api/payments/webhook ────────────────────────────────────────────────

class WebhookResponse(BaseModel):
    received: bool = True


class WebhookErrorResponse(BaseModel):
    error: Literal["invalid_signature"] = "invalid_signature"


# ── POST /api/trips/{id}/generate ────────────────────────────────────────────

class GenerateTripResponse(BaseModel):
    trip_id: str
    output_id: str
    status: Literal["queued"] = "queued"


class PaymentNotConfirmedResponse(BaseModel):
    error: Literal["payment_not_confirmed"] = "payment_not_confirmed"


# ── GET /api/trips/{id}/status ────────────────────────────────────────────────

OutputStatus = Literal["queued", "running", "done", "failed"]


class TripStatusResponse(BaseModel):
    trip_id: str
    output_id: str
    status: OutputStatus
    error_message: str | None = None


# ── GET /api/trips/{id}/output ────────────────────────────────────────────────

class TripOutputResponse(BaseModel):
    trip_id: str
    pdf_url: str
    docx_url: str


class OutputNotFoundResponse(BaseModel):
    error: Literal["output_not_found"] = "output_not_found"


class OutputNotReadyResponse(BaseModel):
    error: Literal["output_not_ready"] = "output_not_ready"
    status: OutputStatus
