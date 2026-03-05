from __future__ import annotations
from typing import Any
from src.worker.rules_engine import RecommendationCandidate


class StubProvider:
    """Stub implementation for dev/test — no external API calls."""

    def get_recommendations(
        self,
        country: str,
        cities: list[str],
        days: int,
        party_size: str,
        preferences: dict[str, Any],
    ) -> list[RecommendationCandidate]:
        candidates: list[RecommendationCandidate] = []

        for city in cities:
            # Hotels — threshold: 4.0 rating, 100 reviews
            for i in range(12):
                candidates.append(
                    RecommendationCandidate(
                        city=city,
                        type="hotel",
                        name=f"{city} Grand Hotel {i+1}",
                        rating=4.1 + (i % 5) * 0.1,
                        review_count=120 + i * 20,
                        price_hint="€€€" if i < 5 else "€€",
                        source_name="TripAdvisor",
                        source_url=f"https://tripadvisor.com/hotels/{city.lower().replace(' ', '-')}-{i+1}",
                    )
                )

            # Attractions — threshold: 4.0 rating, 500 reviews
            for i in range(12):
                candidates.append(
                    RecommendationCandidate(
                        city=city,
                        type="attraction",
                        name=f"{city} Museum {i+1}",
                        rating=4.2 + (i % 4) * 0.1,
                        review_count=600 + i * 100,
                        price_hint=None,
                        source_name="Google Maps",
                        source_url=f"https://maps.google.com/?q={city.replace(' ', '+')}+museum+{i+1}",
                    )
                )

            # Activities — threshold: 4.0 rating, 500 reviews
            for i in range(12):
                candidates.append(
                    RecommendationCandidate(
                        city=city,
                        type="activity",
                        name=f"{city} Walking Tour {i+1}",
                        rating=4.3 + (i % 3) * 0.1,
                        review_count=550 + i * 80,
                        price_hint="€" if i < 6 else "€€",
                        source_name="GetYourGuide",
                        source_url=f"https://getyourguide.com/s/{city.lower().replace(' ', '-')}-tour-{i+1}",
                    )
                )

            # Restaurants — threshold: 4.2 rating, 200 reviews
            for i in range(12):
                candidates.append(
                    RecommendationCandidate(
                        city=city,
                        type="restaurant",
                        name=f"Osteria {city} {i+1}",
                        rating=4.3 + (i % 4) * 0.1,
                        review_count=250 + i * 30,
                        price_hint="€€" if i < 6 else "€€€",
                        source_name="Google Maps",
                        source_url=f"https://maps.google.com/?q={city.replace(' ', '+')}+restaurant+{i+1}",
                    )
                )

            # Bars — threshold: 4.2 rating, 200 reviews
            for i in range(12):
                candidates.append(
                    RecommendationCandidate(
                        city=city,
                        type="bar",
                        name=f"Bar {city} {i+1}",
                        rating=4.3 + (i % 3) * 0.1,
                        review_count=210 + i * 25,
                        price_hint="€",
                        source_name="Google Maps",
                        source_url=f"https://maps.google.com/?q={city.replace(' ', '+')}+bar+{i+1}",
                    )
                )

        return candidates
