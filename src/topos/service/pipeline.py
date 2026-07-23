"""Pipeline stepper: claim → dispatch → advance. Slice 0.8.

Pure orchestration. Depends on PipelineRepo and StepHandler Protocols only —
never imports a concrete adapter. See ARCHITECTURE.md > The pipeline and
> Layering.
"""

from __future__ import annotations

import logging
from typing import Protocol

from topos.domain.pipeline_fsm import next_state
from topos.domain.types import PipelineRow, PipelineState
from topos.service.ports import PipelineRepo

logger = logging.getLogger(__name__)


class StepHandler(Protocol):
    """A handler for one pipeline state. Idempotent keyed on (artifact_id, state).

    Raise an exception to signal transient failure — the stepper will retry.
    Raise StepFatal to park immediately regardless of attempt count.
    """

    async def __call__(self, row: PipelineRow) -> None: ...


class StepFatal(Exception):
    """A failure that should park immediately, bypassing the retry limit."""


async def _noop_handler(row: PipelineRow) -> None:
    """Default handler: succeed immediately. States without real handlers advance."""
    logger.debug("noop handler for %s state=%s", row.artifact_id, row.state)


async def run_step(
    repo: PipelineRepo,
    row: PipelineRow,
    handler: StepHandler,
) -> None:
    """Execute one handler and commit the transition.

    The claim query already incremented `attempts` — `row.attempts` is the
    post-increment count for THIS attempt.
    """

    try:
        await handler(row)
    except StepFatal as exc:
        outcome = next_state(row.state, ok=False, attempts=999)  # force park
        await repo.advance(row.artifact_id, from_state=row.state, outcome=outcome, error=str(exc))
        logger.warning(
            "parked (fatal) artifact=%s state=%s error=%s",
            row.artifact_id,
            row.state,
            exc,
        )
        return
    except Exception as exc:
        outcome = next_state(row.state, ok=False, attempts=row.attempts)
        await repo.advance(row.artifact_id, from_state=row.state, outcome=outcome, error=str(exc))
        if outcome.park:
            logger.warning(
                "parked artifact=%s state=%s attempts=%d error=%s",
                row.artifact_id,
                row.state,
                row.attempts,
                exc,
            )
        else:
            logger.debug(
                "retry artifact=%s state=%s attempts=%d",
                row.artifact_id,
                row.state,
                row.attempts,
            )
        return

    # Success: advance to next state, reset attempt count for the new state.
    outcome = next_state(row.state, ok=True, attempts=0)
    await repo.advance(row.artifact_id, from_state=row.state, outcome=outcome)
    logger.info(
        "advanced artifact=%s %s → %s",
        row.artifact_id,
        row.state,
        outcome.next_state,
    )


async def step(
    repo: PipelineRepo,
    handlers: dict[PipelineState, StepHandler] | None = None,
) -> bool:
    """Claim one row, dispatch, advance. Returns True if work was done.

    Call this in a loop from the worker entrypoint.
    """

    row = await repo.claim_next()
    if row is None:
        return False

    handler = (handlers or {}).get(row.state, _noop_handler)
    await run_step(repo, row, handler)
    return True
