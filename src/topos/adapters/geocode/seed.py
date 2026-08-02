# ruff: noqa: RUF001
"""Load the generated gazetteer seed.

The curated table in ``geocode/__init__.py`` covers 24 landmarks. Real claims
name places well outside it — Πεύκα, Καλοχώρι, Νερομύλων — so those never
geocoded. This loads a much larger set derived from OpenStreetMap.

The seed is *generated*, not hand-written: coordinates typed from memory would
be unverifiable, which is exactly the fabrication this pipeline exists to avoid.
Refresh it with ``topos-cli gazetteer refresh``.

Curated entries always win over seeded ones — they are hand-checked and carry
higher confidence.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from topos.domain.geo import GeocodeResult, GeoPoint
from topos.domain.types import GeoGranularity

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).with_name("gazetteer.json")

SCHEMA_VERSION = 1

_GRANULARITY = {
    "municipality": GeoGranularity.MUNICIPALITY,
    "neighbourhood": GeoGranularity.NEIGHBOURHOOD,
    "street": GeoGranularity.STREET,
    "address": GeoGranularity.ADDRESS,
}

# OSM-derived, so below the hand-curated entries but above the 0.70 lookup
# threshold. Streets are noisier than settlements: many share a name.
_CONFIDENCE = {
    GeoGranularity.MUNICIPALITY: 0.82,
    GeoGranularity.NEIGHBOURHOOD: 0.80,
    GeoGranularity.STREET: 0.75,
    GeoGranularity.ADDRESS: 0.75,
}


# Nominative -> genitive endings. Greek claims name places in the genitive far
# more often than the nominative ("κοινότητα Πεύκων", "οδός Νερομύλων"), while
# OSM stores the nominative.
#
# Applied to accent-folded names, so accent shifts (Αμπελόκηποι ->
# Αμπελοκήπων) need no special handling. Generating a form that does not exist
# is harmless: it simply never appears in any text, so it never matches. That
# is the whole reason to guess here rather than at lookup time.
_GENITIVE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("οι", ("ων",)),  # Αμπελόκηποι -> Αμπελοκήπων
    ("ες", ("ων",)),  # Συκιές -> Συκιών
    ("ος", ("ου",)),  # Εύοσμος -> Ευόσμου
    ("ας", ("α",)),  # Λαγκαδάς -> Λαγκαδά
    ("ης", ("η",)),
    ("α", ("ας", "ων")),  # Καλαμαριά -> Καλαμαριάς; Πεύκα -> Πεύκων
    ("η", ("ης",)),  # Θεσσαλονίκη -> Θεσσαλονίκης
    ("ι", ("ιου",)),  # Καλοχώρι -> Καλοχωρίου
    ("ο", ("ου",)),
)


def genitive_variants(folded_name: str) -> set[str]:
    """Plausible genitive spellings of an accent-folded nominative name.

    Only the last word is inflected: in "λεωφορος νικης" the head noun carries
    the case, and the rest is already in whatever form OSM recorded.
    """
    if not folded_name:
        return set()

    head, _, last = folded_name.rpartition(" ")
    prefix = f"{head} " if head else ""

    out: set[str] = set()
    for ending, replacements in _GENITIVE_RULES:
        if last.endswith(ending):
            stem = last[: -len(ending)]
            out.update(f"{prefix}{stem}{rep}" for rep in replacements)
    out.discard(folded_name)
    return out


def load_seed(path: Path | None = None) -> dict[str, GeocodeResult]:
    """Return ``{lowercased name: GeocodeResult}`` from the seed file.

    A missing or unreadable seed is not fatal — the curated table still works,
    just with narrower coverage.
    """
    seed_path = path or SEED_PATH
    if not seed_path.exists():
        logger.info("no gazetteer seed at %s; using curated entries only", seed_path)
        return {}

    try:
        raw = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("gazetteer seed at %s is unreadable", seed_path)
        return {}

    if raw.get("schema") != SCHEMA_VERSION:
        logger.warning(
            "gazetteer seed schema %r != %d; ignoring. Re-run `topos-cli gazetteer refresh`",
            raw.get("schema"),
            SCHEMA_VERSION,
        )
        return {}

    out: dict[str, GeocodeResult] = {}
    for entry in raw.get("entries", []):
        parsed = _parse_entry(entry)
        if parsed is None:
            continue
        name, result = parsed
        # First writer wins: entries are emitted most-specific-first.
        out.setdefault(name, result)

    logger.info("loaded %d gazetteer entries from %s", len(out), seed_path)
    return out


def _parse_entry(entry: Any) -> tuple[str, GeocodeResult] | None:
    if not isinstance(entry, dict):
        return None

    name = str(entry.get("name", "")).strip().lower()
    label = str(entry.get("label", "")).strip() or name
    granularity = _GRANULARITY.get(str(entry.get("granularity", "")).lower())
    if not name or granularity is None:
        return None

    try:
        lat = float(entry["lat"])
        lon = float(entry["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    return name, GeocodeResult(
        geom=GeoPoint(lat=lat, lon=lon),
        confidence=_CONFIDENCE[granularity],
        granularity=granularity,
        label=label,
    )
