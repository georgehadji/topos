"""Multi-constituency ABAC tenancy.

Phase 4. Adds per-tenant isolation to the application.

Each source/problem/artifact is tagged with a tenant_id.
Users are assigned to tenants with specific roles.
Access is enforced at the service/interface layer.

This is additive — existing single-tenant code continues to work
by using tenant_id = '' (default).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TenantRole(StrEnum):
    ADMIN = "tenant_admin"
    ANALYST = "tenant_analyst"
    VIEWER = "tenant_viewer"


@dataclass(frozen=True, slots=True)
class Tenant:
    """A constituency tenant."""

    id: str  # e.g. "a_thessalonikis"
    name: str
    gazetteer: str | None = None  # specific gazetteer for this constituency


@dataclass(frozen=True, slots=True)
class TenantMembership:
    """A user's role within a tenant."""

    user_id: str
    tenant_id: str
    role: TenantRole


# Built-in tenants
DEFAULT_TENANTS: dict[str, Tenant] = {
    "a_thessalonikis": Tenant(
        id="a_thessalonikis",
        name="A THEssalonikis",
    ),
}
