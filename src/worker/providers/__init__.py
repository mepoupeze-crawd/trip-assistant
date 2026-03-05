from src.lib.config import Settings
from src.worker.providers.base import RecommendationProvider
from src.worker.providers.stub import StubProvider
from src.worker.providers.google_places import GooglePlacesProvider


def get_provider(settings: Settings) -> RecommendationProvider:
    if settings.recommendation_provider == "google_places":
        if not settings.google_places_api_key:
            raise ValueError(
                "GOOGLE_PLACES_API_KEY must be set when "
                "RECOMMENDATION_PROVIDER=google_places"
            )
        return GooglePlacesProvider(api_key=settings.google_places_api_key)
    return StubProvider()
