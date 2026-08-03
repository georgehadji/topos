"""Authority resolution types: pure domain, no IO.

Mirrors domain/geo.py's shape. An authority is an office, never a person
(constraint L1, ARCHITECTURE.md) — this value object can only ever name an
office, matching that constraint at the type level.
"""

from __future__ import annotations

from dataclasses import dataclass

from topos.domain.types import AuthorityLevel


@dataclass(frozen=True, slots=True)
class AuthorityRef:
    """Result of resolving a claim's authority mention to a known office."""

    id: str  # authority.id (uuid as text — domain stays free of the uuid module)
    name: str
    level: AuthorityLevel
    confidence: float  # 0.0-1.0
