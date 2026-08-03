"""Problem lifecycle. Event-sourced projection logic (ADR-007). Slice 2.x.

Schema shipped in Phase 0 (see migration 001: problem, problem_event,
problem_claim). The automated corroboration/verification pipeline that would
drive CANDIDATE -> CORROBORATED -> VERIFIED -> TRACKED is still a stub — this
table only encodes edges that real callers exercise today: the automated
chain, human approval/rejection (RecommendationService bypasses corroboration
because a human sign-off substitutes for it), and ER merges (service/er.py).
"""

from __future__ import annotations

from topos.domain.types import ProblemStatus

# Valid status transitions. Enforced here, not in SQL, so it is unit-testable
# without a database. See ARCHITECTURE.md > functional core.
_ALLOWED: dict[ProblemStatus, frozenset[ProblemStatus]] = {
    ProblemStatus.CANDIDATE: frozenset(
        {
            ProblemStatus.CORROBORATED,
            ProblemStatus.TRACKED,  # human approval (RecommendationService.approve)
            ProblemStatus.RESOLVED,  # human rejection (RecommendationService.reject)
            ProblemStatus.MERGED,  # ER merge into another problem (service/er.py)
        }
    ),
    ProblemStatus.CORROBORATED: frozenset({ProblemStatus.VERIFIED, ProblemStatus.CANDIDATE}),
    ProblemStatus.VERIFIED: frozenset({ProblemStatus.TRACKED}),
    ProblemStatus.TRACKED: frozenset({ProblemStatus.ACTED_UPON}),
    ProblemStatus.ACTED_UPON: frozenset({ProblemStatus.RESOLVED, ProblemStatus.RECURRING}),
    ProblemStatus.RESOLVED: frozenset({ProblemStatus.RECURRING}),
    ProblemStatus.RECURRING: frozenset({ProblemStatus.TRACKED}),
    ProblemStatus.MERGED: frozenset(),  # terminal — revert_merge restores status explicitly
}


def can_transition(current: ProblemStatus, target: ProblemStatus) -> bool:
    """Pure guard. Raising vs. returning False is the caller's choice."""
    return target in _ALLOWED.get(current, frozenset())
