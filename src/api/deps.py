"""FastAPI dependencies — authentication and shared utilities.

X-API-Key guard:
- Missing or wrong key → 403 Forbidden (not 401, not 500 — contract C7)
- Uses constant-time comparison to prevent timing attacks
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status
from fastapi.security import APIKeyHeader

from src.lib.config import settings

_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Dependency that enforces X-API-Key authentication.

    Raises HTTP 403 (not 401) on missing or wrong key — matches C7 contract.
    Uses hmac.compare_digest to prevent timing-based key enumeration.
    """
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing X-API-Key header",
        )

    # Constant-time comparison — prevents timing oracle on key prefix
    if not hmac.compare_digest(x_api_key, settings.internal_api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid X-API-Key",
        )
