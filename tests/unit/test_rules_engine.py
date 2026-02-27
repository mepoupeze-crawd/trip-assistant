"""Unit tests for the Quality Thresholds Rules Engine (C6).

Contract (C6):
  hotel:              rating >= 4.0, review_count >= 100
  attraction/activity: rating >= 4.0, review_count >= 500
  restaurant/bar:     rating >= 4.2, review_count >= 200

Pure unit tests — no DB, no HTTP, no external calls.
"""

from __future__ import annotations

import pytest

from src.worker.rules_engine import (
    RecommendationCandidate,
    check_budget_feasibility,
    filter_recommendations,
    passes_threshold,
    THRESHOLDS,
)


def make_candidate(type_: str, rating: float, review_count: int, city: str = "Rome") -> RecommendationCandidate:
    return RecommendationCandidate(
        city=city,
        type=type_,
        name=f"Test {type_} {rating}",
        rating=rating,
        review_count=review_count,
        price_hint="€€",
        source_name="Google Maps",
        source_url="https://maps.google.com",
    )


class TestHotelThresholds:
    def test_hotel_passes_when_above_threshold(self):
        c = make_candidate("hotel", 4.5, 200)
        assert passes_threshold(c) is True

    def test_hotel_fails_when_rating_too_low(self):
        c = make_candidate("hotel", 3.9, 200)
        assert passes_threshold(c) is False

    def test_hotel_fails_when_reviews_too_low(self):
        c = make_candidate("hotel", 4.5, 50)
        assert passes_threshold(c) is False

    def test_hotel_fails_at_rating_just_below_threshold(self):
        c = make_candidate("hotel", 3.99, 200)
        assert passes_threshold(c) is False

    def test_hotel_fails_at_reviews_just_below_threshold(self):
        c = make_candidate("hotel", 4.0, 99)
        assert passes_threshold(c) is False

    def test_hotel_passes_at_exact_threshold(self):
        c = make_candidate("hotel", 4.0, 100)
        assert passes_threshold(c) is True

    def test_hotel_fails_when_both_below_threshold(self):
        c = make_candidate("hotel", 3.5, 50)
        assert passes_threshold(c) is False


class TestAttractionThresholds:
    def test_attraction_passes_when_above_threshold(self):
        c = make_candidate("attraction", 4.2, 600)
        assert passes_threshold(c) is True

    def test_attraction_fails_when_reviews_below_500(self):
        c = make_candidate("attraction", 4.5, 499)
        assert passes_threshold(c) is False

    def test_attraction_passes_at_exact_500_reviews(self):
        c = make_candidate("attraction", 4.0, 500)
        assert passes_threshold(c) is True

    def test_activity_uses_same_threshold_as_attraction(self):
        assert THRESHOLDS["activity"] == THRESHOLDS["attraction"]

    def test_activity_fails_when_reviews_below_500(self):
        c = make_candidate("activity", 4.5, 300)
        assert passes_threshold(c) is False

    def test_attraction_fails_when_rating_below_4(self):
        c = make_candidate("attraction", 3.9, 1000)
        assert passes_threshold(c) is False


class TestRestaurantThresholds:
    def test_restaurant_passes_when_above_threshold(self):
        c = make_candidate("restaurant", 4.5, 300)
        assert passes_threshold(c) is True

    def test_restaurant_requires_higher_rating_than_hotel(self):
        # Hotel passes at 4.0; restaurant requires 4.2
        c = make_candidate("restaurant", 4.1, 300)
        assert passes_threshold(c) is False

    def test_restaurant_passes_at_exact_42_rating(self):
        c = make_candidate("restaurant", 4.2, 200)
        assert passes_threshold(c) is True

    def test_restaurant_fails_when_reviews_below_200(self):
        c = make_candidate("restaurant", 4.5, 199)
        assert passes_threshold(c) is False

    def test_bar_uses_same_threshold_as_restaurant(self):
        assert THRESHOLDS["bar"] == THRESHOLDS["restaurant"]

    def test_bar_fails_when_rating_below_42(self):
        c = make_candidate("bar", 4.1, 500)
        assert passes_threshold(c) is False


class TestBudgetOverflow:
    def test_allows_mixed_hotel_when_budget_tight(self):
        result = check_budget_feasibility(
            hotel_pref="5star",
            days=10,
            party_size="solo",
            budget_per_person_brl=5000,  # very tight
        )
        assert result["over_budget"] is True
        assert result["mixed_nights"] > 0

    def test_no_adjustment_when_within_budget(self):
        result = check_budget_feasibility(
            hotel_pref="mixed",
            days=7,
            party_size="couple",
            budget_per_person_brl=50000,  # generous
        )
        assert result["over_budget"] is False
        assert result["mixed_nights"] == 0

    def test_logs_justification_when_adjusting(self):
        result = check_budget_feasibility(
            hotel_pref="5star",
            days=14,
            party_size="solo",
            budget_per_person_brl=3000,
        )
        if result["over_budget"]:
            assert result["justification"] is not None
            assert "budget" in result["justification"].lower()


class TestExpansionFallback:
    def test_expand_radius_when_fewer_than_10_results(self):
        few_candidates = [make_candidate("hotel", 4.5, 200) for _ in range(5)]
        result = filter_recommendations(few_candidates, "hotel", "Venice")
        assert result.fallback_needed is True
        assert result.fallback_reason is not None

    def test_no_fallback_needed_when_10_or_more_pass(self):
        many = [make_candidate("hotel", 4.5, 200) for _ in range(12)]
        result = filter_recommendations(many, "hotel", "Rome")
        assert result.fallback_needed is False

    def test_reduce_list_with_justification_as_last_resort(self):
        # 3 pass, 7 fail — fallback should be triggered
        passing = [make_candidate("hotel", 4.5, 200) for _ in range(3)]
        failing = [make_candidate("hotel", 2.0, 10) for _ in range(7)]
        result = filter_recommendations(passing + failing, "hotel", "Naples")
        assert result.fallback_needed is True
        assert len(result.passing) == 3
        assert len(result.rejected) == 7

    def test_swap_city_when_expansion_insufficient(self):
        # This is documented as a flag in the fallback_reason
        only_1 = [make_candidate("restaurant", 4.5, 300)]
        result = filter_recommendations(only_1, "restaurant", "Siena")
        assert result.fallback_needed is True
        assert "expand radius" in result.fallback_reason.lower() or "action" in result.fallback_reason.lower()
