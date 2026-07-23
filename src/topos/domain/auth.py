"""Auth types — roles and identity.

Slice 1.11. Four roles:
- admin: full access
- analyst: search, view, create review tasks
- reviewer: view + resolve review tasks
- viewer: read-only search + view
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


@dataclass(frozen=True, slots=True)
class User:
    """Authenticated user."""

    sub: str  # OIDC subject (user ID)
    email: str
    name: str
    roles: frozenset[Role]
