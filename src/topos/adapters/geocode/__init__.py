"""Geocoding chain: gazetteer → alias → trigram → Nominatim → LLM last resort.

Slice 1.8. Each step tries to resolve a toponym; the chain falls through
to the next step if the previous one returns below a confidence threshold.

See ARCHITECTURE.md §Greek and §Repository layout.
"""

from __future__ import annotations

import re

from topos.domain.geo import GeocodeResult, GeoPoint
from topos.domain.types import GeoGranularity

# ── Thessaloniki gazetteer: curated entries for the constituency ────────────
# Toponyms relevant to A' Thessalonikis. Sources: official municipality
# boundaries, neighbourhood names, major landmarks.
# TODO: import from a seed file or migration (Phase 1.7).
_GAZETTEER: dict[str, GeocodeResult] = {
    "θεσσαλονίκη": GeocodeResult(
        geom=GeoPoint(lat=40.6403, lon=22.9439),
        confidence=0.99,
        granularity=GeoGranularity.MUNICIPALITY,
        label="Θεσσαλονίκη",
    ),
    "κέντρο θεσσαλονίκης": GeocodeResult(
        geom=GeoPoint(lat=40.6324, lon=22.9410),
        confidence=0.90,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Κέντρο Θεσσαλονίκης",
    ),
    "τούμπα": GeocodeResult(
        geom=GeoPoint(lat=40.6124, lon=22.9610),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Τούμπα",
    ),
    "άνω τούμπα": GeocodeResult(
        geom=GeoPoint(lat=40.6140, lon=22.9570),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Άνω Τούμπα",
    ),
    "χαριλάου": GeocodeResult(
        geom=GeoPoint(lat=40.6050, lon=22.9650),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Χαριλάου",
    ),
    "τσιμισκή": GeocodeResult(
        geom=GeoPoint(lat=40.6324, lon=22.9440),
        confidence=0.80,
        granularity=GeoGranularity.STREET,
        label="Οδός Τσιμισκή",
    ),
    "εγνατία": GeocodeResult(
        geom=GeoPoint(lat=40.6320, lon=22.9480),
        confidence=0.80,
        granularity=GeoGranularity.STREET,
        label="Οδός Εγνατία",
    ),
    "λεωφόρος νίκης": GeocodeResult(
        geom=GeoPoint(lat=40.6310, lon=22.9400),
        confidence=0.80,
        granularity=GeoGranularity.STREET,
        label="Λεωφόρος Νίκης",
    ),
    "πλατεία αριστοτέλους": GeocodeResult(
        geom=GeoPoint(lat=40.6330, lon=22.9420),
        confidence=0.90,
        granularity=GeoGranularity.ADDRESS,
        label="Πλατεία Αριστοτέλους",
    ),
    "πλατεία ναβαρίνου": GeocodeResult(
        geom=GeoPoint(lat=40.6350, lon=22.9440),
        confidence=0.85,
        granularity=GeoGranularity.ADDRESS,
        label="Πλατεία Ναβαρίνου",
    ),
    "καλαμαριά": GeocodeResult(
        geom=GeoPoint(lat=40.5820, lon=22.9530),
        confidence=0.90,
        granularity=GeoGranularity.MUNICIPALITY,
        label="Καλαμαριά",
    ),
    "αμπελόκηποι": GeocodeResult(
        geom=GeoPoint(lat=40.6550, lon=22.9270),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Αμπελόκηποι",
    ),
    "ευκαρπία": GeocodeResult(
        geom=GeoPoint(lat=40.6700, lon=22.9200),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Ευκαρπία",
    ),
    "πολίχνη": GeocodeResult(
        geom=GeoPoint(lat=40.6800, lon=22.9350),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Πολίχνη",
    ),
    "σταυρούπολη": GeocodeResult(
        geom=GeoPoint(lat=40.6650, lon=22.9280),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Σταυρούπολη",
    ),
    "συκιές": GeocodeResult(
        geom=GeoPoint(lat=40.6500, lon=22.9300),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Συκιές",
    ),
    "νεάπολη": GeocodeResult(
        geom=GeoPoint(lat=40.6600, lon=22.9380),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Νεάπολη",
    ),
    "πυλαία": GeocodeResult(
        geom=GeoPoint(lat=40.6000, lon=22.9700),
        confidence=0.85,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Πυλαία",
    ),
    "χορτιάτης": GeocodeResult(
        geom=GeoPoint(lat=40.6100, lon=23.1000),
        confidence=0.80,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Χορτιάτης",
    ),
    "πανόραμα": GeocodeResult(
        geom=GeoPoint(lat=40.5900, lon=23.0300),
        confidence=0.80,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Πανόραμα",
    ),
    "θέρμη": GeocodeResult(
        geom=GeoPoint(lat=40.5500, lon=23.0200),
        confidence=0.80,
        granularity=GeoGranularity.MUNICIPALITY,
        label="Θέρμη",
    ),
    "ωραιόκαστρο": GeocodeResult(
        geom=GeoPoint(lat=40.6700, lon=22.9180),
        confidence=0.85,
        granularity=GeoGranularity.MUNICIPALITY,
        label="Ωραιόκαστρο",
    ),
    "λαγκαδάς": GeocodeResult(
        geom=GeoPoint(lat=40.7500, lon=23.0700),
        confidence=0.80,
        granularity=GeoGranularity.MUNICIPALITY,
        label="Λαγκαδάς",
    ),
    "λιτή": GeocodeResult(
        geom=GeoPoint(lat=40.7800, lon=23.0300),
        confidence=0.80,
        granularity=GeoGranularity.NEIGHBOURHOOD,
        label="Λιτή",
    ),
}

# Genitive → nominative alias table. Created by normalising the most common
# genitive forms of Thessaloniki toponyms. This is deliberately incomplete
# and will grow as the system encounters new forms.
_ALIASES: dict[str, str] = {
    "θεσσαλονίκης": "θεσσαλονίκη",
    "τσιμισκή": "τσιμισκή",  # same in genitive
    "εγνατίας": "εγνατία",
    "τούμπας": "τούμπα",
    "χαριλάου": "χαριλάου",  # same
    "καλαμαριάς": "καλαμαριά",
    "αμπελοκήπων": "αμπελόκηποι",
    "πολίχνης": "πολίχνη",
    "σταυρούπολης": "σταυρούπολη",
    "νεάπολης": "νεάπολη",
    "πυλαίας": "πυλαία",
    "θέρμης": "θέρμη",
    "ωραιοκάστρου": "ωραιόκαστρο",
    "λαγκαδά": "λαγκαδάς",
}


_CONFIDENCE_THRESHOLD = 0.70


def geocode(toponym: str) -> GeocodeResult | None:
    """Geocode a Greek toponym using the in-memory gazetteer + alias table.

    Steps:
    1. Exact match in gazetteer (case-insensitive)
    2. Normalise via alias table and retry
    3. Accent-folding: strip Greek accents and retry
    4. Trigram similarity via Postgres (delegated to the DB adapter)
    5. Nominatim / LLM fallback (not implemented yet)

    Returns None if the toponym cannot be resolved.
    """
    cleaned = toponym.strip().lower()

    # Normalize: strip trailing numbers or alphanumeric suffixes
    # (e.g. "Εγνατία 45" -> "Εγνατία", "Εγνατία ac08" -> "Εγνατία")
    cleaned = re.sub(r"\s+[\w\d]+$", "", cleaned).strip()

    # Step 1: exact match
    result = _exact_lookup(cleaned)
    if result and result.confidence >= _CONFIDENCE_THRESHOLD:
        return result

    # Step 2: alias normalisation
    aliased = _ALIASES.get(cleaned)
    if aliased:
        result = _exact_lookup(aliased)
        if result and result.confidence >= _CONFIDENCE_THRESHOLD:
            return GeocodeResult(
                geom=result.geom,
                confidence=result.confidence * 0.95,  # slight penalty for alias
                granularity=result.granularity,
                label=result.label,
            )

    # Step 3: accent folding (rough: strip tonos)
    # Greek vowels with tonos: άέήίόύώ -> αεηιουω
    accent_map = str.maketrans("άέήίόύώ", "αεηιουω")
    unaccented = cleaned.translate(accent_map)
    if unaccented != cleaned:
        result = _exact_lookup(unaccented)
        if result and result.confidence >= _CONFIDENCE_THRESHOLD:
            return GeocodeResult(
                geom=result.geom,
                confidence=result.confidence * 0.85,  # penalty for accent mismatch
                granularity=result.granularity,
                label=result.label,
            )
        # Also try with alias after accent folding
        aliased_unaccented = _ALIASES.get(unaccented)
        if aliased_unaccented:
            result = _exact_lookup(aliased_unaccented)
            if result and result.confidence >= _CONFIDENCE_THRESHOLD:
                return GeocodeResult(
                    geom=result.geom,
                    confidence=result.confidence * 0.80,
                    granularity=result.granularity,
                    label=result.label,
                )

    # TODO step 4: trigram via Postgres (needs DB adapter)
    # TODO step 5: Nominatim / LLM fallback (needs http client)

    return None


def _exact_lookup(name: str) -> GeocodeResult | None:
    """Look up a normalised name in the gazetteer, case-insensitive."""
    return _GAZETTEER.get(name)
