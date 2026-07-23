"""Pipeline state transitions as a pure function. Slice 0.7.

The stepper (service/pipeline.py) claims a row and calls `next_state`. This
module owns the transition table and nothing else — no DB, no locking, no
retry policy. Tested with literal inputs/outputs in tests/unit/test_pipeline_fsm.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from topos.domain.types import PipelineState

# Linear happy path. A step that fails does not move state; the stepper
# increments `attempts` and reschedules `run_after` (see ARCHITECTURE.md).
_ORDER: tuple[PipelineState, ...] = (
    PipelineState.FETCHED,
    PipelineState.TEXTIFIED,
    PipelineState.CHUNKED,
    PipelineState.EXTRACTED,
    PipelineState.GEOCODED,
    PipelineState.RESOLVED,
    PipelineState.INDEXED,
    PipelineState.DONE,
)

MAX_ATTEMPTS = 5


class InvalidTransition(ValueError):
    """Raised when a step tries to advance from a state it cannot reach."""


@dataclass(frozen=True, slots=True)
class StepOutcome:
    next_state: PipelineState
    park: bool = False


def next_state(current: PipelineState, *, ok: bool, attempts: int) -> StepOutcome:
    """Pure transition. No IO, no clock — `attempts` is passed in by the caller.

    - `current == DONE` or `PARKED`: terminal, raises. The stepper's claim
      query never selects these rows, so reaching here is a caller bug.
    - `ok=False` and `attempts >= MAX_ATTEMPTS`: park for human review.
    - `ok=False` and attempts remain: stay in `current` (caller reschedules).
    - `ok=True`: advance one step in `_ORDER`.
    """
    if current in (PipelineState.DONE, PipelineState.PARKED):
        raise InvalidTransition(f"{current} is terminal")

    if not ok:
        if attempts >= MAX_ATTEMPTS:
            return StepOutcome(next_state=PipelineState.PARKED, park=True)
        return StepOutcome(next_state=current)

    idx = _ORDER.index(current)
    if idx + 1 >= len(_ORDER):
        raise InvalidTransition(f"{current} has no successor in _ORDER")
    return StepOutcome(next_state=_ORDER[idx + 1])
