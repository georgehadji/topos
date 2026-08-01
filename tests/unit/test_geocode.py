"""Unit tests: geocoding chain.

Tests geocode() with the in-memory gazetteer, alias table,
and accent-folding fallback. No IO.
"""

from __future__ import annotations

from topos.adapters.geocode import _ALIASES, _GAZETTEER, geocode
from topos.domain.types import GeoGranularity


def test_gazetteer_has_entries() -> None:
    assert len(_GAZETTEER) >= 20


def test_alias_table_has_entries() -> None:
    assert len(_ALIASES) >= 10


def test_exact_match_thessaloniki() -> None:
    result = geocode("\u03b8\u03b5\u03c3\u03c3\u03b1\u03bb\u03bf\u03bd\u03af\u03ba\u03b7")
    assert result is not None
    assert result.confidence > 0.70
    assert result.granularity == GeoGranularity.MUNICIPALITY
    assert "\u0398\u03b5\u03c3\u03c3\u03b1\u03bb\u03bf\u03bd\u03af\u03ba\u03b7" in result.label


def test_alias_genitive_to_nominative() -> None:
    """Genitive should resolve via alias."""
    result = geocode("\u03b8\u03b5\u03c3\u03c3\u03b1\u03bb\u03bf\u03bd\u03af\u03ba\u03b7\u03c2")
    assert result is not None
    assert result.confidence > 0.65


def test_alias_neighbourhood() -> None:
    result = geocode("\u03c4\u03bf\u03cd\u03bc\u03c0\u03b1\u03c2")
    assert result is not None
    assert 0.70 < result.confidence <= 0.85


def test_street_level_granularity() -> None:
    result = geocode("\u03c4\u03c3\u03b9\u03bc\u03b9\u03c3\u03ba\u03ae")
    assert result is not None
    assert result.granularity == GeoGranularity.STREET


def test_unknown_toponym_returns_none() -> None:
    result = geocode("nonexistent_place_xyz")
    assert result is None


def test_empty_string_returns_none() -> None:
    result = geocode("")
    assert result is None


def test_kalamaria_municipality() -> None:
    result = geocode("\u03ba\u03b1\u03bb\u03b1\u03bc\u03b1\u03c1\u03b9\u03ac")
    assert result is not None
    assert result.granularity == GeoGranularity.MUNICIPALITY


def test_egnatia_street() -> None:
    result = geocode("\u03b5\u03b3\u03bd\u03b1\u03c4\u03af\u03b1")
    assert result is not None
    assert result.granularity == GeoGranularity.STREET


def test_panorama() -> None:
    result = geocode("\u03c0\u03b1\u03bd\u03cc\u03c1\u03b1\u03bc\u03b1")
    assert result is not None
    assert result.granularity == GeoGranularity.NEIGHBOURHOOD


def test_accent_folding_code_points() -> None:
    """Verify the accent-folding translation map works with codepoints."""
    accent_map = {
        0x03AC: 0x03B1,  # a -> alpha
        0x03AD: 0x03B5,  # e -> epsilon
        0x03AE: 0x03B7,  # e -> eta
        0x03AF: 0x03B9,  # i -> iota
        0x03CC: 0x03BF,  # o -> omicron
        0x03CD: 0x03C5,  # u -> upsilon
        0x03CE: 0x03C9,  # o -> omega
    }
    # θεσσαλονίκη with tonos
    with_accent = "\u03b8\u03b5\u03c3\u03c3\u03b1\u03bb\u03bf\u03bd\u03af\u03ba\u03b7"
    # θεσσαλονικη without tonos
    without_accent = "\u03b8\u03b5\u03c3\u03c3\u03b1\u03bb\u03bf\u03bd\u03b9\u03ba\u03b7"
    result = with_accent.translate(accent_map)
    assert result == without_accent, f"{result!r} != {without_accent!r}"


def test_geocoding_with_numbers_and_suffixes() -> None:
    """Verify that streets with house numbers or alpha-numeric suffixes are geocoded successfully."""
    # Egnatia 45
    res1 = geocode("Εγνατία 45")
    assert res1 is not None
    assert res1.granularity == GeoGranularity.STREET
    assert res1.label == "Οδός Εγνατία"

    # Egnatia ac08
    res2 = geocode("Εγνατία ac08")
    assert res2 is not None
    assert res2.granularity == GeoGranularity.STREET

    # Tsimiski 12
    res3 = geocode("Τσιμισκή 12")
    assert res3 is not None
    assert res3.granularity == GeoGranularity.STREET
