from __future__ import annotations
from typing import Any
import httpx
import structlog
from src.worker.rules_engine import RecommendationCandidate

log = structlog.get_logger(__name__)


class GooglePlacesProvider:
    """Google Places Text Search API v1 provider."""

    BASE_URL = "https://places.googleapis.com/v1/places:searchText"

    PLACE_TYPES: dict[str, str] = {
        "hotel": "lodging",
        "attraction": "tourist_attraction",
        "activity": "amusement_park",
        "restaurant": "restaurant",
        "bar": "bar",
    }

    PRICE_MAP: dict[int, str] = {1: "€", 2: "€€", 3: "€€€", 4: "€€€€"}

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

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
            for rec_type, place_type in self.PLACE_TYPES.items():
                text_query = f"{rec_type} in {city}"
                try:
                    results = self._search(text_query, place_type)
                    for place in results:
                        candidate = self._map_place(place, city, rec_type)
                        if candidate:
                            candidates.append(candidate)
                except httpx.HTTPError:
                    # Task retry logic (3× backoff) handles this — just re-raise
                    log.error(
                        "google_places_request_failed",
                        city=city,
                        rec_type=rec_type,
                    )
                    raise

        return candidates

    def _search(self, text_query: str, place_type: str) -> list[dict[str, Any]]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.rating,"
                "places.userRatingCount,places.priceLevel"
            ),
        }
        payload = {
            "textQuery": text_query,
            "includedType": place_type,
            "languageCode": "en",
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(self.BASE_URL, json=payload, headers=headers)
            resp.raise_for_status()
        return resp.json().get("places", [])

    def _map_place(
        self, place: dict[str, Any], city: str, rec_type: str
    ) -> RecommendationCandidate | None:
        place_id = place.get("id")
        name = (place.get("displayName") or {}).get("text")
        if not name or not place_id:
            return None

        price_level = place.get("priceLevel")
        price_hint = self.PRICE_MAP.get(price_level) if price_level else None

        return RecommendationCandidate(
            city=city,
            type=rec_type,
            name=name,
            rating=place.get("rating"),
            review_count=place.get("userRatingCount"),
            price_hint=price_hint,
            source_name="Google Maps",
            source_url=f"https://maps.google.com/?place_id={place_id}",
        )
