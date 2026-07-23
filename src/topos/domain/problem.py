"""Problem lifecycle. Event-sourced projection logic (ADR-007). Slice 2.x.

STUB — schema ships in Phase 0 (see migration 001: problem, problem_event,
problem_claim), the algorithm ships in Phase 2. Do not implement ahead of
docs/PROGRESS.md; a half-built state machine is worse than an honest stub.
"""

from __future__ import annotations

from topos.domain.types import ProblemStatus

# Valid status transitions. Enforced here, not in SQL, so it is unit-testable
# without a database. See ARCHITECTURE.md > functional core.
_ALLOWED: dict[ProblemStatus, frozenset[ProblemStatus]] = {
    ProblemStatus.CANDIDATE: frozenset({ProblemStatus.CORROBORATED}),
    ProblemStatus.CORROBORATED: frozenset({ProblemStatus.VERIFIED, ProblemStatus.CANDIDATE}),
    ProblemStatus.VERIFIED: frozenset({ProblemStatus.TRACKED}),
    ProblemStatus.TRACKED: frozenset({ProblemStatus.ACTED_UPON}),
    ProblemStatus.ACTED_UPON: frozenset({ProblemStatus.RESOLVED, ProblemStatus.RECURRING}),
    ProblemStatus.RESOLVED: frozenset({ProblemStatus.RECURRING}),
    ProblemStatus.RECURRING: frozenset({ProblemStatus.TRACKED}),
}


def can_transition(current: ProblemStatus, target: ProblemStatus) -> bool:
    """Pure guard. Raising vs. returning False is the caller's choice."""
    return target in _ALLOWED.get(current, frozenset())
