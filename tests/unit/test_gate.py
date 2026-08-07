# ruff: noqa: RUF001
"""Unit tests: extraction gate (Phase 6 #6.2, #6.3).

ADR-014's rule extends here: a refusal must carry a reason, never a bare
False indistinguishable from "extracted nothing".
"""

from __future__ import annotations

from topos.domain.gate import should_extract
from topos.domain.simhash import simhash

_LOCAL_TEXT = "Διακοπή υδροδότησης στη Σταυρούπολη λόγω βλάβης στο δίκτυο ύδρευσης"
_OUT_OF_AREA_TEXT = "Η πυρκαγιά στη Δυτική Αττική επεκτείνεται προς την Αθήνα"


def test_out_of_area_text_is_refused_with_reason() -> None:
    decision = should_extract(_OUT_OF_AREA_TEXT)
    assert decision.extract is False
    assert decision.reason == "out_of_area"


def test_local_text_with_no_recent_hashes_is_accepted() -> None:
    decision = should_extract(_LOCAL_TEXT)
    assert decision.extract is True
    assert decision.reason is None


def test_near_duplicate_of_a_recent_hash_is_refused() -> None:
    already_seen = simhash(_LOCAL_TEXT)
    decision = should_extract(_LOCAL_TEXT, recent_hashes=(already_seen,))
    assert decision.extract is False
    assert decision.reason == "near_duplicate"


def test_unrelated_recent_hash_does_not_trigger_a_refusal() -> None:
    unrelated = simhash("Το δημοτικό συμβούλιο ενέκρινε τον προϋπολογισμό για έργα υποδομής")
    decision = should_extract(_LOCAL_TEXT, recent_hashes=(unrelated,))
    assert decision.extract is True


def test_out_of_area_wins_over_near_duplicate_check() -> None:
    """Relevance is checked first — an out-of-area near-duplicate is still
    reported as out_of_area, the more informative reason."""
    already_seen = simhash(_OUT_OF_AREA_TEXT)
    decision = should_extract(_OUT_OF_AREA_TEXT, recent_hashes=(already_seen,))
    assert decision.reason == "out_of_area"
