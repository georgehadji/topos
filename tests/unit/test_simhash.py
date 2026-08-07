# ruff: noqa: RUF001
"""Unit tests: simhash fingerprinting (Phase 6 #6.3)."""

from __future__ import annotations

from topos.domain.simhash import hamming, simhash


def test_identical_text_hashes_identically() -> None:
    text = "Διακοπή υδροδότησης στη Σταυρούπολη λόγω βλάβης στο δίκτυο"
    assert simhash(text) == simhash(text)
    assert hamming(simhash(text), simhash(text)) == 0


def test_near_identical_text_has_small_hamming_distance() -> None:
    a = "Διακοπή υδροδότησης στη Σταυρούπολη λόγω βλάβης στο δίκτυο ύδρευσης"
    b = "Διακοπή υδροδότησης στη Σταυρούπολη λόγω βλάβης στο δίκτυο αποχέτευσης"
    assert hamming(simhash(a), simhash(b)) <= 5


def test_unrelated_text_has_large_hamming_distance() -> None:
    a = "Διακοπή υδροδότησης στη Σταυρούπολη λόγω βλάβης στο δίκτυο ύδρευσης"
    b = "Το δημοτικό συμβούλιο ενέκρινε τον προϋπολογισμό για έργα υποδομής"
    assert hamming(simhash(a), simhash(b)) > 5


def test_hamming_is_symmetric() -> None:
    a, b = simhash("πρώτο κείμενο"), simhash("δεύτερο κείμενο")
    assert hamming(a, b) == hamming(b, a)


def test_empty_text_is_deterministic() -> None:
    assert simhash("") == simhash("")
