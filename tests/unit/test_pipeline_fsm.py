"""Literal inputs, literal outputs. No mocks — this is why domain/ is pure.
See ARCHITECTURE.md > functional core.
"""

import pytest

from topos.domain.pipeline_fsm import MAX_ATTEMPTS, InvalidTransition, next_state
from topos.domain.types import PipelineState


def test_ok_advances_one_step() -> None:
    outcome = next_state(PipelineState.FETCHED, ok=True, attempts=0)
    assert outcome.next_state == PipelineState.TEXTIFIED
    assert outcome.park is False


def test_full_happy_path_reaches_done() -> None:
    state = PipelineState.FETCHED
    for _ in range(len(list(PipelineState)) - 2):  # exclude DONE, PARKED
        outcome = next_state(state, ok=True, attempts=0)
        state = outcome.next_state
        if state == PipelineState.DONE:
            break
    assert state == PipelineState.DONE


def test_failure_below_threshold_stays_put() -> None:
    outcome = next_state(PipelineState.EXTRACTED, ok=False, attempts=1)
    assert outcome.next_state == PipelineState.EXTRACTED
    assert outcome.park is False


def test_failure_at_threshold_parks() -> None:
    outcome = next_state(PipelineState.EXTRACTED, ok=False, attempts=MAX_ATTEMPTS)
    assert outcome.next_state == PipelineState.PARKED
    assert outcome.park is True


@pytest.mark.parametrize("terminal", [PipelineState.DONE, PipelineState.PARKED])
def test_terminal_states_raise(terminal: PipelineState) -> None:
    with pytest.raises(InvalidTransition):
        next_state(terminal, ok=True, attempts=0)


def test_last_real_state_has_no_successor_beyond_done() -> None:
    outcome = next_state(PipelineState.INDEXED, ok=True, attempts=0)
    assert outcome.next_state == PipelineState.DONE
