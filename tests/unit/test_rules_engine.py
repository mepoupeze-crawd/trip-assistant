"""Unit tests for the Quality Thresholds Rules Engine (C6).

Contract (from C6):
  - hotel: rating >= 4.0 AND review_count >= 100
  - attraction/activity: rating >= 4.0 AND review_count >= 500
  - restaurant/bar: rating >= 4.2 AND review_count >= 200
  - If < 10 items pass thresholds: expand radius → swap city → reduce list
    (log justification in output)

These tests are pure unit tests — no DB, no HTTP, no external calls.
The rules engine module is expected at ``src.lib.rules_engine``.

All tests are marked ``skip`` until the backend implements the module.
Remove the skip marker on each test class as the implementation lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Adapter: import rules engine or skip the whole module gracefully.
# ---------------------------------------------------------------------------

try:
    from src.lib.rules_engine import (  # type: ignore[import]
        RulesEngine,
        ThresholdResult,
    )

    _RULES_ENGINE_AVAILABLE = True
except ImportError:
    _RULES_ENGINE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _RULES_ENGINE_AVAILABLE,
    reason="src.lib.rules_engine not yet implemented — backend agent pending",
)


# ---------------------------------------------------------------------------
# Helpers / stub data builders
# ---------------------------------------------------------------------------


@dataclass
class RecommendationStub:
    """Minimal stand-in for a Recommendation ORM row in rules engine tests."""

    type: str
    rating: float
    review_count: int
    name: str = "Test Place"
    city: str = "Rome"


def hotel(rating: float, reviews: int) -> RecommendationStub:
    return RecommendationStub(type="hotel", rating=rating, review_count=reviews)


def attraction(rating: float, reviews: int) -> RecommendationStub:
    return RecommendationStub(type="attraction", rating=rating, review_count=reviews)


def activity(rating: float, reviews: int) -> RecommendationStub:
    return RecommendationStub(type="activity", rating=rating, review_count=reviews)


def restaurant(rating: float, reviews: int) -> RecommendationStub:
    return RecommendationStub(type="restaurant", rating=rating, review_count=reviews)


def bar(rating: float, reviews: int) -> RecommendationStub:
    return RecommendationStub(type="bar", rating=rating, review_count=reviews)


# ---------------------------------------------------------------------------
# TestHotelThresholds
# ---------------------------------------------------------------------------


class TestHotelThresholds:
    """hotel: rating >= 4.0 AND review_count >= 100"""

    def test_hotel_passes_when_above_threshold(self):
        # Arrange
        rec = hotel(rating=4.5, reviews=200)
        engine = RulesEngine()
        # Act
        result: ThresholdResult = engine.evaluate(rec)
        # Assert
        assert result.passes is True, "Hotel with rating=4.5, reviews=200 should pass"

    def test_hotel_fails_when_rating_too_low(self):
        # Arrange
        rec = hotel(rating=3.9, reviews=200)
        engine = RulesEngine()
        # Act
        result: ThresholdResult = engine.evaluate(rec)
        # Assert
        assert result.passes is False, "Hotel with rating=3.9 should fail (min 4.0)"

    def test_hotel_fails_when_reviews_too_low(self):
        # Arrange
        rec = hotel(rating=4.5, reviews=50)
        engine = RulesEngine()
        # Act
        result: ThresholdResult = engine.evaluate(rec)
        # Assert
        assert result.passes is False, "Hotel with reviews=50 should fail (min 100)"

    def test_hotel_fails_at_rating_just_below_threshold(self):
        # Arrange: 3.99 is one step below 4.0
        rec = hotel(rating=3.99, reviews=100)
        engine = RulesEngine()
        # Act
        result: ThresholdResult = engine.evaluate(rec)
        # Assert
        assert result.passes is False, "Hotel with rating=3.99 should fail"

    def test_hotel_fails_at_reviews_just_below_threshold(self):
        # Arrange: 99 is one step below 100
        rec = hotel(rating=4.0, reviews=99)
        engine = RulesEngine()
        # Act
        result: ThresholdResult = engine.evaluate(rec)
        # Assert
        assert result.passes is False, "Hotel with reviews=99 should fail"

    def test_hotel_passes_at_exact_threshold(self):
        # Arrange: exactly on the boundary — should pass (>= semantics)
        rec = hotel(rating=4.0, reviews=100)
        engine = RulesEngine()
        # Act
        result: ThresholdResult = engine.evaluate(rec)
        # Assert
        assert result.passes is True, (
            "Hotel at exactly rating=4.0, reviews=100 should pass (>= boundary)"
        )

    def test_hotel_fails_when_both_below_threshold(self):
        # Arrange
        rec = hotel(rating=3.0, reviews=10)
        engine = RulesEngine()
        # Act
        result: ThresholdResult = engine.evaluate(rec)
        # Assert
        assert result.passes is False


# ---------------------------------------------------------------------------
# TestAttractionThresholds
# ---------------------------------------------------------------------------


class TestAttractionThresholds:
    """attraction/activity: rating >= 4.0 AND review_count >= 500"""

    def test_attraction_passes_when_above_threshold(self):
        rec = attraction(rating=4.5, reviews=600)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is True

    def test_attraction_fails_when_reviews_below_500(self):
        # Note: attraction requires 500 reviews (stricter than hotel's 100)
        rec = attraction(rating=4.5, reviews=499)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is False, (
            "Attraction with reviews=499 should fail (min 500 for attractions)"
        )

    def test_attraction_passes_at_exact_500_reviews(self):
        rec = attraction(rating=4.0, reviews=500)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is True

    def test_activity_uses_same_threshold_as_attraction(self):
        # activity and attraction share the same threshold group
        rec_activity = activity(rating=4.0, reviews=500)
        rec_attraction = attraction(rating=4.0, reviews=500)
        engine = RulesEngine()
        assert engine.evaluate(rec_activity).passes == engine.evaluate(rec_attraction).passes

    def test_activity_fails_when_reviews_below_500(self):
        rec = activity(rating=4.5, reviews=200)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is False

    def test_attraction_fails_when_rating_below_4(self):
        rec = attraction(rating=3.9, reviews=1000)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is False


# ---------------------------------------------------------------------------
# TestRestaurantThresholds
# ---------------------------------------------------------------------------


class TestRestaurantThresholds:
    """restaurant/bar: rating >= 4.2 AND review_count >= 200"""

    def test_restaurant_passes_when_above_threshold(self):
        rec = restaurant(rating=4.5, reviews=300)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is True

    def test_restaurant_requires_higher_rating_than_hotel(self):
        # Restaurant min is 4.2; a rating of 4.1 passes hotel but fails restaurant
        rec = restaurant(rating=4.1, reviews=300)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is False, (
            "Restaurant with rating=4.1 should fail (min 4.2 for restaurants)"
        )

    def test_restaurant_passes_at_exact_42_rating(self):
        rec = restaurant(rating=4.2, reviews=200)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is True

    def test_restaurant_fails_when_reviews_below_200(self):
        rec = restaurant(rating=4.5, reviews=199)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is False

    def test_bar_uses_same_threshold_as_restaurant(self):
        rec_bar = bar(rating=4.2, reviews=200)
        rec_restaurant = restaurant(rating=4.2, reviews=200)
        engine = RulesEngine()
        assert engine.evaluate(rec_bar).passes == engine.evaluate(rec_restaurant).passes

    def test_bar_fails_when_rating_below_42(self):
        rec = bar(rating=4.1, reviews=500)
        engine = RulesEngine()
        result = engine.evaluate(rec)
        assert result.passes is False


# ---------------------------------------------------------------------------
# TestBudgetOverflow
# ---------------------------------------------------------------------------


class TestBudgetOverflow:
    """Rules engine budget adjustment behaviour."""

    def test_allows_mixed_hotel_when_budget_tight(self):
        """When estimated cost exceeds budget, engine should suggest mixing hotels."""
        engine = RulesEngine()
        # Arrange: tight budget scenario — trigger adjustment logic
        result = engine.evaluate_budget(
            budget_per_person_brl=5000,
            estimated_cost_per_person_brl=7000,
            days=10,
        )
        # Assert: engine returns an adjustment recommendation (1-2 mixed nights)
        assert result.adjusted is True
        assert result.justification is not None and len(result.justification) > 0

    def test_no_adjustment_when_within_budget(self):
        engine = RulesEngine()
        result = engine.evaluate_budget(
            budget_per_person_brl=30000,
            estimated_cost_per_person_brl=15000,
            days=10,
        )
        assert result.adjusted is False

    def test_logs_justification_when_adjusting(self):
        """Adjustment results must always carry a human-readable justification."""
        engine = RulesEngine()
        result = engine.evaluate_budget(
            budget_per_person_brl=5000,
            estimated_cost_per_person_brl=9000,
            days=7,
        )
        assert result.justification, "Justification must be non-empty when adjustment occurs"


# ---------------------------------------------------------------------------
# TestExpansionFallback
# ---------------------------------------------------------------------------


class TestExpansionFallback:
    """Fallback chain when fewer than 10 recommendations pass quality thresholds."""

    def test_expand_radius_when_fewer_than_10_results(self):
        """Should trigger radius expansion when passing count < 10."""
        engine = RulesEngine()
        # Arrange: 5 passing recommendations → below threshold
        passing = [hotel(4.5, 200) for _ in range(5)]
        result = engine.apply_fallback(city="Venice", passing_recommendations=passing)
        # Assert: engine signals expand_radius as the chosen strategy
        assert result.strategy == "expand_radius"
        assert result.justification is not None

    def test_swap_city_when_expansion_insufficient(self):
        """Should swap city when radius expansion still yields < 10 results."""
        engine = RulesEngine()
        # Arrange: simulate that expansion was tried and returned only 3 results
        result = engine.apply_fallback(
            city="Venice",
            passing_recommendations=[hotel(4.5, 200) for _ in range(3)],
            expansion_tried=True,
            expansion_result_count=3,
        )
        assert result.strategy == "swap_city"
        assert result.justification is not None

    def test_reduce_list_with_justification_as_last_resort(self):
        """When both expansion and swap fail, should reduce list and log justification."""
        engine = RulesEngine()
        result = engine.apply_fallback(
            city="Venice",
            passing_recommendations=[hotel(4.5, 200) for _ in range(2)],
            expansion_tried=True,
            expansion_result_count=2,
            swap_tried=True,
            swap_result_count=2,
        )
        assert result.strategy == "reduce_list"
        assert result.justification is not None
        assert "reduce" in result.justification.lower() or result.justification

    def test_no_fallback_needed_when_10_or_more_pass(self):
        """Should not apply any fallback when 10+ recommendations already pass."""
        engine = RulesEngine()
        passing = [hotel(4.5, 200) for _ in range(10)]
        result = engine.apply_fallback(city="Rome", passing_recommendations=passing)
        assert result.strategy is None or result.strategy == "none"
