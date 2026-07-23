"""Geocoding types: pure domain, no IO.

Every geocode result returns (geom, confidence, granularity) — never a
bare point (ARCHITECTURE.md §Greek).
"""

from __future__ import annotations

from dataclasses import dataclass

from topos.domain.types import GeoGranularity


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """A geocoded location with uncertainty."""

    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class GeocodeResult:
    """Result of geocoding a toponym.

    Never a bare point — always carries confidence and granularity
    so the UI can draw uncertainty (ARCHITECTURE.md §Greek).
    """

    geom: GeoPoint
    confidence: float  # 0.0-1.0
    granularity: GeoGranularity
    label: str = ""  # human-readable name of the matched location


@dataclass(frozen=True, slots=True)
class GazetteerEntry:
    """One row in the Thessaloniki gazetteer.

    A named location with its geometry and any known aliases.
    """

    name: str  # canonical name in Greek
    geom: GeoPoint
    granularity: GeoGranularity
    aliases: tuple[str, ...] = ()  # alternative names / genitive forms
