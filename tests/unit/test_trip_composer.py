"""Unit tests for the Trip Composer — city/day distribution logic.

The composer is expected at ``src.lib.trip_composer``.
All tests are skipped until the backend agent implements the module.

Test strategy: pure unit tests — no DB, no HTTP, no filesystem.
Input is a trip record (or dict matching the Trip schema), output is a
structured itinerary (days × cities × activities).
"""

from __future__ import annotations

import pytest

try:
    from src.lib.trip_composer import TripComposer  # type: ignore[import]

    _COMPOSER_AVAILABLE = True
except ImportError:
    _COMPOSER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _COMPOSER_AVAILABLE,
    reason="src.lib.trip_composer not yet implemented — backend agent pending",
)


def _trip(
    *,
    days: int = 10,
    country: str = "Italy",
    party_size: str = "couple",
    preferences: dict | None = None,
) -> dict:
    return {
        "days": days,
        "country": country,
        "party_size": party_size,
        "preferences_json": preferences
        or {
            "pace": "medium",
            "focus": ["food", "culture"],
            "crowds": "high",
            "hotel": "mixed",
            "restrictions": [],
        },
    }


class TestCityDistribution:
    """Days should be distributed sensibly across multiple cities."""

    def test_single_city_for_short_trip(self):
        # 3-day trip → likely 1 city (not enough time to split)
        composer = TripComposer()
        itinerary = composer.compose(_trip(days=3))
        assert len(itinerary.cities) == 1

    def test_multiple_cities_for_longer_trip(self):
        # 10-day trip → at least 2 cities
        composer = TripComposer()
        itinerary = composer.compose(_trip(days=10))
        assert len(itinerary.cities) >= 2

    def test_total_days_matches_input(self):
        composer = TripComposer()
        itinerary = composer.compose(_trip(days=7))
        total = sum(city.days_allocated for city in itinerary.cities)
        assert total == 7, f"Expected 7 days total, got {total}"

    def test_no_city_gets_zero_days(self):
        composer = TripComposer()
        itinerary = composer.compose(_trip(days=10))
        for city in itinerary.cities:
            assert city.days_allocated > 0, f"City {city.name} has 0 days"

    def test_cities_are_in_requested_country(self):
        composer = TripComposer()
        itinerary = composer.compose(_trip(days=14, country="France"))
        # Each city should be in France (or a known region of France)
        for city in itinerary.cities:
            assert city.country == "France", (
                f"City {city.name} is in {city.country}, expected France"
            )


class TestPaceDistribution:
    """Daily activity count should reflect the requested pace."""

    def test_light_pace_has_fewer_activities_per_day(self):
        composer = TripComposer()
        light = composer.compose(_trip(preferences={"pace": "light", "focus": ["culture"], "crowds": "low", "hotel": "5star", "restrictions": []}))
        intense = composer.compose(_trip(preferences={"pace": "intense", "focus": ["culture"], "crowds": "high", "hotel": "mixed", "restrictions": []}))

        avg_light = sum(len(d.activities) for d in light.days) / len(light.days)
        avg_intense = sum(len(d.activities) for d in intense.days) / len(intense.days)
        assert avg_light < avg_intense, (
            "Light pace should have fewer daily activities than intense pace"
        )

    def test_intense_pace_has_more_activities_per_day(self):
        composer = TripComposer()
        itinerary = composer.compose(
            _trip(preferences={"pace": "intense", "focus": ["food", "culture", "nature"], "crowds": "high", "hotel": "mixed", "restrictions": []})
        )
        for day in itinerary.days:
            assert len(day.activities) >= 3, (
                f"Intense pace day should have >= 3 activities, got {len(day.activities)}"
            )


class TestFocusFiltering:
    """Trip focus should influence which recommendation types are included."""

    def test_food_focus_includes_restaurants(self):
        composer = TripComposer()
        itinerary = composer.compose(
            _trip(preferences={"pace": "medium", "focus": ["food"], "crowds": "high", "hotel": "mixed", "restrictions": []})
        )
        all_types = [a.type for day in itinerary.days for a in day.activities]
        assert "restaurant" in all_types or "bar" in all_types

    def test_culture_focus_includes_attractions(self):
        composer = TripComposer()
        itinerary = composer.compose(
            _trip(preferences={"pace": "medium", "focus": ["culture"], "crowds": "high", "hotel": "mixed", "restrictions": []})
        )
        all_types = [a.type for day in itinerary.days for a in day.activities]
        assert "attraction" in all_types


class TestPartySize:
    """Party size may affect hotel room type suggestions."""

    def test_couple_generates_double_room_hint(self):
        composer = TripComposer()
        itinerary = composer.compose(_trip(party_size="couple"))
        hotels = [a for day in itinerary.days for a in day.activities if a.type == "hotel"]
        if hotels:
            assert any("double" in (h.price_hint or "").lower() or h.party_size_hint == "couple" for h in hotels)

    def test_solo_generates_single_room_hint(self):
        composer = TripComposer()
        itinerary = composer.compose(_trip(party_size="solo"))
        hotels = [a for day in itinerary.days for a in day.activities if a.type == "hotel"]
        if hotels:
            assert any("single" in (h.price_hint or "").lower() or h.party_size_hint == "solo" for h in hotels)
