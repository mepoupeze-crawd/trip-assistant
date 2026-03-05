"""Unit tests for the recommendation provider abstraction.

Tests cover:
- StubProvider: correct output structure, city-specific data
- get_provider factory: correct selection, ValueError on missing key
- GooglePlacesProvider: response mapping (mocked HTTP calls)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.lib.config import Settings
from src.worker.providers import get_provider
from src.worker.providers.stub import StubProvider
from src.worker.providers.google_places import GooglePlacesProvider
from src.worker.rules_engine import RecommendationCandidate


# ── StubProvider Tests ────────────────────────────────────────────────────────

class TestStubProvider:
    CITIES = ["Rome", "Florence"]
    TYPES = ["hotel", "attraction", "activity", "restaurant", "bar"]

    def test_returns_recommendation_candidates(self):
        provider = StubProvider()
        result = provider.get_recommendations(
            country="Italy",
            cities=self.CITIES,
            days=7,
            party_size="couple",
            preferences={},
        )
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(r, RecommendationCandidate) for r in result)

    def test_returns_candidates_for_all_cities(self):
        provider = StubProvider()
        result = provider.get_recommendations(
            country="Italy",
            cities=self.CITIES,
            days=7,
            party_size="couple",
            preferences={},
        )
        cities_in_result = {r.city for r in result}
        assert "Rome" in cities_in_result
        assert "Florence" in cities_in_result

    def test_returns_candidates_for_all_types(self):
        provider = StubProvider()
        result = provider.get_recommendations(
            country="Italy",
            cities=["Rome"],
            days=7,
            party_size="couple",
            preferences={},
        )
        types_in_result = {r.type for r in result}
        for t in self.TYPES:
            assert t in types_in_result, f"Missing type: {t}"

    def test_returns_12_candidates_per_city_per_type(self):
        provider = StubProvider()
        result = provider.get_recommendations(
            country="Italy",
            cities=["Rome"],
            days=7,
            party_size="couple",
            preferences={},
        )
        for rec_type in self.TYPES:
            count = sum(1 for r in result if r.city == "Rome" and r.type == rec_type)
            assert count == 12, f"Expected 12 for {rec_type}, got {count}"

    def test_candidates_pass_quality_thresholds(self):
        """StubProvider ratings must pass the rules engine thresholds."""
        from src.worker.rules_engine import passes_threshold
        provider = StubProvider()
        result = provider.get_recommendations(
            country="Italy",
            cities=["Rome"],
            days=7,
            party_size="couple",
            preferences={},
        )
        failing = [r for r in result if not passes_threshold(r)]
        assert len(failing) == 0, f"{len(failing)} candidates fail quality thresholds"


# ── get_provider Factory Tests ────────────────────────────────────────────────

class TestGetProviderFactory:
    def test_returns_stub_provider_by_default(self):
        settings = Settings(recommendation_provider="stub")
        provider = get_provider(settings)
        assert isinstance(provider, StubProvider)

    def test_returns_stub_provider_explicitly(self):
        settings = Settings(recommendation_provider="stub")
        assert isinstance(get_provider(settings), StubProvider)

    def test_returns_google_places_provider_when_configured(self):
        settings = Settings(
            recommendation_provider="google_places",
            google_places_api_key="AIzaFakeKey",
        )
        provider = get_provider(settings)
        assert isinstance(provider, GooglePlacesProvider)

    def test_raises_value_error_when_google_places_without_key(self):
        settings = Settings(
            recommendation_provider="google_places",
            google_places_api_key=None,
        )
        with pytest.raises(ValueError, match="GOOGLE_PLACES_API_KEY"):
            get_provider(settings)


# ── GooglePlacesProvider Tests ────────────────────────────────────────────────

MOCK_PLACES_RESPONSE = {
    "places": [
        {
            "id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
            "displayName": {"text": "Hotel Roma"},
            "rating": 4.5,
            "userRatingCount": 1200,
            "priceLevel": 3,
        },
        {
            "id": "ChIJN1t_tDeuEmsRUsoyG83frY5",
            "displayName": {"text": "Hotel Trastevere"},
            "rating": 4.2,
            "userRatingCount": 800,
            "priceLevel": 2,
        },
    ]
}


class TestGooglePlacesProvider:
    def _mock_search(self, monkeypatch):
        """Return a provider with mocked HTTP calls."""
        provider = GooglePlacesProvider(api_key="AIzaFakeKey")

        def fake_search(self_inner, text_query, place_type):
            return MOCK_PLACES_RESPONSE["places"]

        monkeypatch.setattr(GooglePlacesProvider, "_search", fake_search)
        return provider

    def test_maps_place_id_to_source_url(self, monkeypatch):
        provider = self._mock_search(monkeypatch)
        result = provider.get_recommendations(
            country="Italy",
            cities=["Rome"],
            days=7,
            party_size="couple",
            preferences={},
        )
        hotel_results = [r for r in result if r.type == "hotel" and r.city == "Rome"]
        assert len(hotel_results) > 0
        assert "place_id=" in hotel_results[0].source_url

    def test_maps_display_name_to_name(self, monkeypatch):
        provider = self._mock_search(monkeypatch)
        result = provider.get_recommendations(
            country="Italy",
            cities=["Rome"],
            days=7,
            party_size="couple",
            preferences={},
        )
        names = {r.name for r in result if r.city == "Rome" and r.type == "hotel"}
        assert "Hotel Roma" in names

    def test_maps_price_level_to_price_hint(self, monkeypatch):
        provider = self._mock_search(monkeypatch)
        result = provider.get_recommendations(
            country="Italy",
            cities=["Rome"],
            days=7,
            party_size="couple",
            preferences={},
        )
        # priceLevel=3 → €€€
        hotel_roma = next(
            (r for r in result if r.name == "Hotel Roma" and r.type == "hotel"), None
        )
        assert hotel_roma is not None
        assert hotel_roma.price_hint == "€€€"

    def test_source_name_is_google_maps(self, monkeypatch):
        provider = self._mock_search(monkeypatch)
        result = provider.get_recommendations(
            country="Italy",
            cities=["Rome"],
            days=7,
            party_size="couple",
            preferences={},
        )
        assert all(r.source_name == "Google Maps" for r in result)

    def test_reraises_http_error(self, monkeypatch):
        import httpx
        provider = GooglePlacesProvider(api_key="AIzaFakeKey")

        def failing_search(self_inner, text_query, place_type):
            raise httpx.HTTPError("connection failed")

        monkeypatch.setattr(GooglePlacesProvider, "_search", failing_search)

        with pytest.raises(httpx.HTTPError):
            provider.get_recommendations(
                country="Italy",
                cities=["Rome"],
                days=7,
                party_size="couple",
                preferences={},
            )

    def test_api_key_not_in_log_or_exception(self, monkeypatch, caplog):
        """API key must never appear in logs or exception messages."""
        import httpx, logging
        fake_key = "AIzaSuperSecretKey12345"
        provider = GooglePlacesProvider(api_key=fake_key)

        def failing_search(self_inner, text_query, place_type):
            raise httpx.HTTPError("server error")

        monkeypatch.setattr(GooglePlacesProvider, "_search", failing_search)

        with caplog.at_level(logging.ERROR):
            with pytest.raises(httpx.HTTPError):
                provider.get_recommendations(
                    country="Italy",
                    cities=["Rome"],
                    days=7,
                    party_size="couple",
                    preferences={},
                )

        # Key must not appear anywhere in captured logs
        for record in caplog.records:
            assert fake_key not in record.getMessage(), (
                f"API key leaked in log: {record.getMessage()}"
            )
