from __future__ import annotations
from typing import Any, Protocol
from src.worker.rules_engine import RecommendationCandidate


class RecommendationProvider(Protocol):
    """Contract for all recommendation data sources.

    Implementations must be stateless between calls.
    All errors must be raised as exceptions (caller handles retry logic).
    """

    def get_recommendations(
        self,
        country: str,
        cities: list[str],
        days: int,
        party_size: str,
        preferences: dict[str, Any],
    ) -> list[RecommendationCandidate]:
        """Return recommendation candidates for the given trip parameters.

        Returns raw candidates — the rules engine applies quality thresholds.
        Must return at least 1 candidate per city × type combination, ideally 10+.
        """
        ...
