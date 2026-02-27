"""Rules Engine — quality thresholds and budget logic (C6 contract).

Quality thresholds:
  hotel:          rating >= 4.0, review_count >= 100
  attraction:     rating >= 4.0, review_count >= 500
  activity:       rating >= 4.0, review_count >= 500
  restaurant:     rating >= 4.2, review_count >= 200
  bar:            rating >= 4.2, review_count >= 200

Fallback strategy when < 10 items pass threshold:
  1. Expand radius (flag for data layer to retry with wider search)
  2. Swap city (flag for trip_composer to try adjacent city)
  3. Reduce list (accept however many pass — log justification)
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from typing import Any

log = structlog.get_logger(__name__)

# ── C6 Quality Thresholds ─────────────────────────────────────────────────────

THRESHOLDS: dict[str, dict[str, float | int]] = {
    "hotel": {"min_rating": 4.0, "min_reviews": 100},
    "attraction": {"min_rating": 4.0, "min_reviews": 500},
    "activity": {"min_rating": 4.0, "min_reviews": 500},
    "restaurant": {"min_rating": 4.2, "min_reviews": 200},
    "bar": {"min_rating": 4.2, "min_reviews": 200},
}

MIN_PASSING_ITEMS = 10


@dataclass
class RecommendationCandidate:
    """Raw candidate from any data source before threshold filtering."""

    city: str
    type: str  # hotel | attraction | activity | restaurant | bar
    name: str
    rating: float | None
    review_count: int | None
    price_hint: str | None
    source_name: str
    source_url: str

    # Extra metadata used by fallback logic
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FilterResult:
    """Result of applying thresholds to a list of candidates."""

    passing: list[RecommendationCandidate]
    rejected: list[RecommendationCandidate]
    fallback_needed: bool
    fallback_reason: str | None = None


def passes_threshold(candidate: RecommendationCandidate) -> bool:
    """Return True if the candidate meets quality thresholds for its type."""
    thresholds = THRESHOLDS.get(candidate.type)
    if thresholds is None:
        # Unknown type — pass through (log a warning)
        log.warning("unknown_recommendation_type", type=candidate.type)
        return True

    rating = candidate.rating
    reviews = candidate.review_count

    if rating is None or reviews is None:
        return False

    return (
        rating >= thresholds["min_rating"]
        and reviews >= thresholds["min_reviews"]
    )


def filter_recommendations(
    candidates: list[RecommendationCandidate],
    rec_type: str,
    city: str,
) -> FilterResult:
    """Apply quality threshold to a list of candidates for a given type/city.

    If fewer than MIN_PASSING_ITEMS pass, sets fallback_needed=True and logs
    the justification so it can be tracked in observability tooling.
    """
    passing = [c for c in candidates if passes_threshold(c)]
    rejected = [c for c in candidates if not passes_threshold(c)]

    fallback_needed = len(passing) < MIN_PASSING_ITEMS
    fallback_reason: str | None = None

    if fallback_needed:
        fallback_reason = (
            f"Only {len(passing)} items passed threshold for "
            f"type={rec_type}, city={city}. "
            f"Action: expand radius → swap city → reduce list."
        )
        log.warning(
            "quality_threshold_fallback",
            type=rec_type,
            city=city,
            passing_count=len(passing),
            rejected_count=len(rejected),
            fallback_reason=fallback_reason,
        )

    return FilterResult(
        passing=passing,
        rejected=rejected,
        fallback_needed=fallback_needed,
        fallback_reason=fallback_reason,
    )


# ── Budget Logic ──────────────────────────────────────────────────────────────

# Rough nightly cost estimates per hotel category (BRL)
HOTEL_NIGHTLY_BRL: dict[str, int] = {
    "5star": 2500,
    "boutique": 1500,
    "mixed": 900,
}


def estimate_hotel_cost(
    hotel_pref: str,
    days: int,
    party_size: str,
) -> int:
    """Estimate total hotel cost in BRL for the trip.

    party_size 'couple' splits cost per person (1 room / 2 people).
    """
    nightly = HOTEL_NIGHTLY_BRL.get(hotel_pref, HOTEL_NIGHTLY_BRL["mixed"])
    nights = days - 1  # last day is departure — no accommodation
    if party_size == "couple":
        # One room shared — cost per person is half
        nightly = nightly // 2
    return nightly * max(nights, 1)


def check_budget_feasibility(
    hotel_pref: str,
    days: int,
    party_size: str,
    budget_per_person_brl: int,
) -> dict[str, Any]:
    """Assess if hotel preference fits within budget.

    If over budget:
    - Allow 1-2 nights at "mixed" to compensate.
    - Prefer neighborhood swap over must-see removal.
    - Log justification.

    Returns a dict with feasibility analysis and any recommendation overrides.
    """
    estimated = estimate_hotel_cost(hotel_pref, days, party_size)
    # Hotel is typically ~40% of trip budget
    hotel_budget_share = int(budget_per_person_brl * 0.40)
    over_budget = estimated > hotel_budget_share

    result: dict[str, Any] = {
        "hotel_pref": hotel_pref,
        "estimated_hotel_cost_brl": estimated,
        "hotel_budget_share_brl": hotel_budget_share,
        "over_budget": over_budget,
        "adjusted_hotel_pref": hotel_pref,
        "mixed_nights": 0,
        "justification": None,
    }

    if over_budget and hotel_pref != "mixed":
        # Allow 1-2 mixed nights to bring cost down
        mixed_nights = min(2, days // 3)
        adjusted_pref = hotel_pref  # keep preference for most nights
        justification = (
            f"Hotel preference '{hotel_pref}' exceeds budget share "
            f"(estimated BRL {estimated} vs budget BRL {hotel_budget_share}). "
            f"Substituting {mixed_nights} night(s) with 'mixed' category. "
            f"Preferring neighborhood swap over must-see removal."
        )
        log.info(
            "budget_adjustment",
            hotel_pref=hotel_pref,
            mixed_nights=mixed_nights,
            justification=justification,
        )
        result["mixed_nights"] = mixed_nights
        result["justification"] = justification

    return result
