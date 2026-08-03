"""Unit tests: problem status transition guard.

Pure domain — literal inputs, literal expected outputs, no mocks.
can_transition had zero callers before RecommendationService and service/er.py
were wired to use it; this locks in the edges those callers depend on.
"""

from __future__ import annotations

from topos.domain.problem import can_transition
from topos.domain.types import ProblemStatus


def test_candidate_to_corroborated_is_legal() -> None:
    assert can_transition(ProblemStatus.CANDIDATE, ProblemStatus.CORROBORATED) is True


def test_candidate_to_tracked_is_legal_human_approval() -> None:
    """RecommendationService.approve() substitutes human sign-off for the
    automated corroboration/verification chain."""
    assert can_transition(ProblemStatus.CANDIDATE, ProblemStatus.TRACKED) is True


def test_candidate_to_resolved_is_legal_human_rejection() -> None:
    """RecommendationService.reject() — there is no dedicated REJECTED status."""
    assert can_transition(ProblemStatus.CANDIDATE, ProblemStatus.RESOLVED) is True


def test_candidate_to_merged_is_legal_er_merge() -> None:
    assert can_transition(ProblemStatus.CANDIDATE, ProblemStatus.MERGED) is True


def test_candidate_to_acted_upon_is_illegal() -> None:
    """Skipping straight past tracked has no real caller and should stay illegal."""
    assert can_transition(ProblemStatus.CANDIDATE, ProblemStatus.ACTED_UPON) is False


def test_tracked_to_acted_upon_is_legal_export() -> None:
    assert can_transition(ProblemStatus.TRACKED, ProblemStatus.ACTED_UPON) is True


def test_merged_is_terminal_in_the_normal_lifecycle() -> None:
    """revert_merge restores status directly, bypassing this guard on purpose
    (documented in service/er.py) — nothing should transition out of MERGED
    through the normal state machine."""
    for target in ProblemStatus:
        assert can_transition(ProblemStatus.MERGED, target) is False


def test_unknown_source_status_has_no_legal_targets() -> None:
    assert can_transition(ProblemStatus.RECURRING, ProblemStatus.CANDIDATE) is False
