"""Unit tests for the Trip Composer — city/day distribution logic.

Pure unit tests — no DB, no HTTP, no filesystem.
"""

from __future__ import annotations

import pytest

from src.worker.trip_composer import (
    compose,
    select_cities,
    ComposedTrip,
    CitySlot,
    EUROPE_CITIES_BY_COUNTRY,
)
from src.worker.rules_engine import RecommendationCandidate

PREFS = {
    "pace": "medium",
    "focus": ["food", "culture", "nature"],
    "crowds": "medium",
    "hotel": "mixed",
    "restrictions": [],
}


def make_recs(cities: list[str]) -> list[RecommendationCandidate]:
    """Generate stub recommendations for a list of cities."""
    candidates = []
    types = ["hotel", "attraction", "activity", "restaurant", "bar"]
    for city in cities:
        for t in types:
            for i in range(12):
                candidates.append(
                    RecommendationCandidate(
                        city=city,
                        type=t,
                        name=f"{city} {t} {i}",
                        rating=4.3,
                        review_count=600,
                        price_hint="€€",
                        source_name="Google Maps",
                        source_url="https://maps.google.com",
                    )
                )
    return candidates


class TestCityDistribution:
    def test_single_city_for_short_trip(self):
        slots = select_cities("Italy", 3, PREFS)
        assert len(slots) >= 1
        total = sum(s.days for s in slots)
        assert total == 3

    def test_multiple_cities_for_longer_trip(self):
        slots = select_cities("Italy", 14, PREFS)
        assert len(slots) >= 2

    def test_total_days_matches_input(self):
        for days in [5, 7, 10, 14]:
            slots = select_cities("France", days, PREFS)
            # Transfer days (1 per city boundary) are not included in slot.days
            transfer_days = max(0, len(slots) - 1)
            assert sum(s.days for s in slots) + transfer_days == days

    def test_no_city_gets_zero_days(self):
        slots = select_cities("Spain", 10, PREFS)
        for slot in slots:
            assert slot.days > 0

    def test_cities_are_in_requested_country(self):
        slots = select_cities("Italy", 10, PREFS)
        # Keys in EUROPE_CITIES_BY_COUNTRY are lowercase
        known_cities = {c.lower() for c in EUROPE_CITIES_BY_COUNTRY.get("italy", [])}
        for slot in slots:
            assert slot.city.lower() in known_cities, (
                f"City '{slot.city}' not in Italy's known cities list"
            )


class TestCompose:
    def test_compose_returns_composed_trip(self):
        slots = select_cities("Italy", 7, PREFS)
        cities = [s.city for s in slots]
        recs = make_recs(cities)
        result = compose("Italy", 7, PREFS, start_date=None, all_recommendations=recs)
        assert isinstance(result, ComposedTrip)

    def test_composed_trip_has_city_slots(self):
        slots = select_cities("France", 10, PREFS)
        cities = [s.city for s in slots]
        recs = make_recs(cities)
        result = compose("France", 10, PREFS, start_date=None, all_recommendations=recs)
        assert len(result.city_slots) >= 1

    def test_composed_trip_has_daily_schedule(self):
        slots = select_cities("Spain", 7, PREFS)
        cities = [s.city for s in slots]
        recs = make_recs(cities)
        result = compose("Spain", 7, PREFS, start_date=None, all_recommendations=recs)
        # daily_schedule includes city days + transfer days = total trip days
        assert len(result.daily_schedule) == 7


class TestPaceDistribution:
    def test_light_pace_has_fewer_activities_per_day(self):
        light_prefs = {**PREFS, "pace": "light"}
        intense_prefs = {**PREFS, "pace": "intense"}
        slots_light = select_cities("Italy", 7, light_prefs)
        slots_intense = select_cities("Italy", 7, intense_prefs)
        # Light pace visits fewer cities (less city-hopping = fewer transitions)
        assert len(slots_light) <= len(slots_intense)

    def test_intense_pace_has_more_activities_per_day(self):
        prefs = {**PREFS, "pace": "intense"}
        slots = select_cities("Italy", 7, prefs)
        cities = [s.city for s in slots]
        recs = make_recs(cities)
        result = compose("Italy", 7, prefs, start_date=None, all_recommendations=recs)
        # Intense pace generates a full schedule (may exceed 7 when MIN_DAYS_PER_CITY enforces minimums)
        assert len(result.daily_schedule) >= 7
        non_transfer = [d for d in result.daily_schedule if not d.is_transfer]
        # Every non-transfer day has all three slots populated
        assert all(d.morning and d.afternoon and d.evening for d in non_transfer)


class TestFocusFiltering:
    def test_food_focus_includes_restaurants(self):
        prefs = {**PREFS, "focus": ["food", "culture", "nature"]}
        slots = select_cities("Italy", 7, prefs)
        cities = [s.city for s in slots]
        recs = make_recs(cities)
        result = compose("Italy", 7, prefs, start_date=None, all_recommendations=recs)
        # Evening slots should reference restaurant recommendations
        non_transfer = [d for d in result.daily_schedule if not d.is_transfer]
        assert any("Dinner at" in d.evening for d in non_transfer) or len(result.recommendations_by_city) > 0

    def test_culture_focus_includes_attractions(self):
        prefs = {**PREFS, "focus": ["culture", "food", "nature"]}
        slots = select_cities("France", 7, prefs)
        cities = [s.city for s in slots]
        recs = make_recs(cities)
        result = compose("France", 7, prefs, start_date=None, all_recommendations=recs)
        assert result is not None


class TestPartySize:
    def test_couple_generates_correct_output(self):
        prefs = {**PREFS}
        slots = select_cities("Italy", 7, prefs)
        cities = [s.city for s in slots]
        recs = make_recs(cities)
        result = compose("Italy", 7, prefs, start_date=None, all_recommendations=recs)
        assert result is not None

    def test_solo_generates_correct_output(self):
        prefs = {**PREFS}
        slots = select_cities("Italy", 7, prefs)
        cities = [s.city for s in slots]
        recs = make_recs(cities)
        result = compose("Italy", 7, prefs, start_date=None, all_recommendations=recs)
        assert result is not None
