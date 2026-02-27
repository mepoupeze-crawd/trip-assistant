"""Unit-test conftest — overrides the session-scoped DB fixture from the root
conftest so that pure unit tests can run without a live PostgreSQL connection.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables() -> AsyncGenerator[None, None]:  # type: ignore[override]
    """No-op override — unit tests are pure Python and need no database."""
    yield
