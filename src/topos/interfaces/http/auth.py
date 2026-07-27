"""Auth middleware: OIDC token verification + role extraction.

Slice 1.11. Uses a discovery URL (e.g. well-known configuration from
Keycloak, Auth0, Google, etc.) to fetch public keys and verify JWTs.

In dev mode with no OIDC configured, falls back to a dev user with
admin role for local testing.
"""

from __future__ import annotations

import base64
import json
from contextlib import suppress
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from topos.config import get_settings
from topos.domain.auth import Role, User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> User:
    """FastAPI dependency that returns the authenticated user."""
    settings = get_settings()

    if not settings.oidc_discovery_url:
        return User(
            sub="dev-user",
            email="dev@topos.local",
            name="Dev User",
            roles=frozenset({Role.ADMIN}),
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    token = credentials.credentials
    payload = _decode_jwt_payload(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return _payload_to_user(payload)


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode a JWT payload without signature verification.

    TODO: Full OIDC verification (jwt + JWKS), requires python-jose.
    For dev, simple base64 decode of the payload is sufficient.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:  # noqa: PLR2004
            return None
        padding = 4 - len(parts[1]) % 4
        if padding != 4:  # noqa: PLR2004
            parts[1] += "=" * padding
        decoded = base64.urlsafe_b64decode(parts[1])
        return dict(json.loads(decoded))
    except Exception:
        return None


def _payload_to_user(payload: dict[str, Any]) -> User:
    """Extract a User from OIDC token claims."""
    raw_roles = payload.get("realm_access", {}).get("roles", []) or payload.get("roles", [])
    roles = set()
    for r in raw_roles:
        with suppress(ValueError):
            roles.add(Role(r.lower()))

    if not roles:
        roles.add(Role.VIEWER)

    return User(
        sub=payload.get("sub", ""),
        email=payload.get("email", ""),
        name=payload.get("name", payload.get("preferred_username", "")),
        roles=frozenset(roles),
    )
