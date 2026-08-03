"""Unit tests: authority resolution.

Tests resolve_authority() with the in-memory alias table. No IO.
"""

from __future__ import annotations

from topos.adapters.authority import _AUTHORITIES, resolve_authority
from topos.domain.types import AuthorityLevel


def test_authorities_table_has_entries() -> None:
    assert len(_AUTHORITIES) >= 5


def test_resolves_greek_acronym() -> None:
    result = resolve_authority("διακοπή λόγω βλάβης — ΕΥΑΘ")
    assert result is not None
    assert result.name == "ΕΥΑΘ"
    assert result.level == AuthorityLevel.UTILITY


def test_resolves_latin_transliteration() -> None:
    result = resolve_authority("reported by EYATH this morning")
    assert result is not None
    assert result.name == "ΕΥΑΘ"


def test_resolves_english_gloss_seen_in_real_extraction() -> None:
    """Extraction has actually returned this exact phrase for a real claim."""
    result = resolve_authority("authority_responsible: EYATH (Water Supply and Sewerage Company)")
    assert result is not None
    assert result.name == "ΕΥΑΘ"


def test_resolves_municipality_genitive() -> None:
    result = resolve_authority("απόφαση του Δήμου Θεσσαλονίκης")
    assert result is not None
    assert result.name == "Δήμος Θεσσαλονίκης"
    assert result.level == AuthorityLevel.MUNICIPALITY


def test_word_boundary_prevents_false_positive() -> None:
    """'dei' must not match inside an unrelated word."""
    assert resolve_authority("ideology and deities are unrelated") is None


def test_no_known_authority_returns_none() -> None:
    assert resolve_authority("a completely unrelated sentence about weather") is None


def test_empty_text_returns_none() -> None:
    assert resolve_authority("") is None
