"""Trip Composer — city/day distribution and daily schedule builder.

Responsibilities:
- Distribute total trip days across cities based on preferences and budget
- Build a daily schedule table (date, city, accommodation, morning/afternoon/evening)
- Apply transfer day logic (travel between cities counts as a day)

The composer works with data already filtered by the rules engine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import structlog

from src.worker.rules_engine import RecommendationCandidate

log = structlog.get_logger(__name__)

# Minimum and maximum days per city to keep itineraries varied
MIN_DAYS_PER_CITY = 2
MAX_DAYS_PER_CITY = 5

# European cities ranked by tourism appeal — used as fallback selection
EUROPE_CITIES_BY_COUNTRY: dict[str, list[str]] = {
    "france": ["Paris", "Lyon", "Marseille", "Nice", "Bordeaux"],
    "italy": ["Rome", "Florence", "Venice", "Milan", "Naples", "Amalfi"],
    "spain": ["Barcelona", "Madrid", "Seville", "Valencia", "Granada"],
    "portugal": ["Lisbon", "Porto", "Sintra", "Algarve"],
    "germany": ["Berlin", "Munich", "Hamburg", "Cologne", "Frankfurt"],
    "netherlands": ["Amsterdam", "Rotterdam", "Utrecht", "The Hague"],
    "austria": ["Vienna", "Salzburg", "Innsbruck"],
    "switzerland": ["Zurich", "Geneva", "Basel", "Lucerne"],
    "greece": ["Athens", "Santorini", "Mykonos", "Thessaloniki"],
    "croatia": ["Dubrovnik", "Split", "Zagreb"],
    "czechia": ["Prague", "Brno"],
    "hungary": ["Budapest"],
    "poland": ["Krakow", "Warsaw", "Gdansk"],
    "denmark": ["Copenhagen"],
    "sweden": ["Stockholm", "Gothenburg"],
    "norway": ["Oslo", "Bergen", "Flam"],
    "iceland": ["Reykjavik"],
    "ireland": ["Dublin", "Galway"],
    "united kingdom": ["London", "Edinburgh", "Bath", "Oxford"],
    "belgium": ["Brussels", "Bruges", "Ghent"],
}


@dataclass
class CitySlot:
    """A city with its allocated days in the itinerary."""

    city: str
    days: int
    start_offset: int  # day number from trip start (0-indexed)


@dataclass
class DaySchedule:
    """A single day's schedule in the itinerary."""

    day_number: int  # 1-indexed
    date_str: str  # dd/mm (weekday) e.g. "15/09 (Tue)"
    city: str
    accommodation: str  # hotel name or "Transfer day"
    morning: str
    afternoon: str
    evening: str
    is_transfer: bool = False


@dataclass
class ComposedTrip:
    """Full composed itinerary ready for document generation."""

    city_slots: list[CitySlot]
    daily_schedule: list[DaySchedule]
    recommendations_by_city: dict[str, dict[str, list[RecommendationCandidate]]]


def select_cities(
    country: str,
    days: int,
    preferences: dict[str, Any],
) -> list[CitySlot]:
    """Select cities and allocate days based on trip length and preferences.

    Strategy:
    - 3-5 days: 1-2 cities
    - 6-10 days: 2-3 cities
    - 11-20 days: 3-5 cities
    - 21-30 days: 5-7 cities

    Respects pace preference: light → fewer cities, intense → more cities.
    """
    pace: str = preferences.get("pace", "medium")
    country_lower = country.lower()

    available_cities = EUROPE_CITIES_BY_COUNTRY.get(country_lower, [country])

    # Determine target city count
    if days <= 5:
        base_count = 1
    elif days <= 10:
        base_count = 2
    elif days <= 20:
        base_count = 3
    else:
        base_count = 5

    # Adjust for pace
    pace_adjustment = {"light": -1, "medium": 0, "intense": 1}
    city_count = max(1, base_count + pace_adjustment.get(pace, 0))
    city_count = min(city_count, len(available_cities))

    selected = available_cities[:city_count]

    # Distribute days — reserve 1 transfer day between each pair of cities
    transfer_days = city_count - 1
    travel_days = days - transfer_days
    base_days = travel_days // city_count
    remainder = travel_days % city_count

    slots: list[CitySlot] = []
    offset = 0
    for i, city in enumerate(selected):
        city_days = base_days + (1 if i < remainder else 0)
        city_days = max(city_days, MIN_DAYS_PER_CITY)
        slots.append(CitySlot(city=city, days=city_days, start_offset=offset))
        offset += city_days
        if i < city_count - 1:
            offset += 1  # transfer day

    log.info(
        "cities_selected",
        country=country,
        days=days,
        pace=pace,
        cities=[s.city for s in slots],
    )

    return slots


def build_daily_schedule(
    city_slots: list[CitySlot],
    start_date: date | None,
    recommendations_by_city: dict[str, dict[str, list[RecommendationCandidate]]],
) -> list[DaySchedule]:
    """Build the day-by-day schedule for the itinerary.

    If start_date is None (user gave month, not dates), uses first day of month
    as reference — actual dates will be confirmed at booking.
    """
    if start_date is None:
        # Use a placeholder date sequence — dates will be labeled "Day N"
        use_placeholder = True
        start_date = date(2026, 1, 1)  # arbitrary — display as offsets
    else:
        use_placeholder = False

    schedule: list[DaySchedule] = []
    current_date = start_date
    day_number = 1

    for i, slot in enumerate(city_slots):
        city_recs = recommendations_by_city.get(slot.city, {})
        hotels = city_recs.get("hotel", [])
        attractions = city_recs.get("attraction", [])
        activities = city_recs.get("activity", [])
        restaurants = city_recs.get("restaurant", [])

        hotel_name = hotels[0].name if hotels else "TBD — search locally"

        for day_in_city in range(slot.days):
            if use_placeholder:
                date_str = f"Day {day_number}"
            else:
                weekday = current_date.strftime("%a")
                date_str = f"{current_date.strftime('%d/%m')} ({weekday})"

            # Assign activities — cycle through available recommendations
            morning_idx = day_in_city * 2
            afternoon_idx = day_in_city * 2 + 1
            evening_idx = day_in_city

            morning_rec = attractions[morning_idx % len(attractions)] if attractions else None
            afternoon_rec = activities[afternoon_idx % len(activities)] if activities else None
            evening_rec = restaurants[evening_idx % len(restaurants)] if restaurants else None

            morning = f"Visit {morning_rec.name}" if morning_rec else f"Explore {slot.city}"
            afternoon = f"{afternoon_rec.name}" if afternoon_rec else f"Free time in {slot.city}"
            evening = f"Dinner at {evening_rec.name}" if evening_rec else f"Dinner in {slot.city}"

            schedule.append(
                DaySchedule(
                    day_number=day_number,
                    date_str=date_str,
                    city=slot.city,
                    accommodation=hotel_name,
                    morning=morning,
                    afternoon=afternoon,
                    evening=evening,
                )
            )

            current_date += timedelta(days=1)
            day_number += 1

        # Transfer day between cities
        if i < len(city_slots) - 1:
            next_city = city_slots[i + 1].city
            if use_placeholder:
                date_str = f"Day {day_number}"
            else:
                weekday = current_date.strftime("%a")
                date_str = f"{current_date.strftime('%d/%m')} ({weekday})"

            schedule.append(
                DaySchedule(
                    day_number=day_number,
                    date_str=date_str,
                    city=f"{slot.city} → {next_city}",
                    accommodation="Transfer day",
                    morning=f"Check-out from {slot.city}",
                    afternoon=f"Travel to {next_city}",
                    evening=f"Check-in {next_city} — rest",
                    is_transfer=True,
                )
            )
            current_date += timedelta(days=1)
            day_number += 1

    return schedule


def compose(
    country: str,
    days: int,
    preferences: dict[str, Any],
    start_date: date | None,
    all_recommendations: list[RecommendationCandidate],
) -> ComposedTrip:
    """Main entry point — compose the full trip itinerary.

    Args:
        country: Destination country
        days: Total trip days
        preferences: C2 preferences dict
        start_date: First day of trip (None if user gave month/year)
        all_recommendations: Filtered recommendations from rules engine

    Returns:
        ComposedTrip with city slots, daily schedule, and grouped recommendations
    """
    city_slots = select_cities(country, days, preferences)

    # Group recommendations by city and type
    recommendations_by_city: dict[str, dict[str, list[RecommendationCandidate]]] = {}
    for rec in all_recommendations:
        city_recs = recommendations_by_city.setdefault(rec.city, {})
        city_recs.setdefault(rec.type, []).append(rec)

    daily_schedule = build_daily_schedule(city_slots, start_date, recommendations_by_city)

    return ComposedTrip(
        city_slots=city_slots,
        daily_schedule=daily_schedule,
        recommendations_by_city=recommendations_by_city,
    )
