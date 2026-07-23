"""Pipeline claim + transition persistence via asyncpg.

Concrete implementation of service.ports.PipelineRepo (slice 0.8).
Raw SQL — no ORM. See ARCHITECTURE.md > Data access and > The pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

from topos.domain.pipeline_fsm import StepOutcome
from topos.domain.types import ArtifactId, PipelineRow, PipelineState


def _row_from_record(r: asyncpg.Record) -> PipelineRow:
    return PipelineRow(
        artifact_id=ArtifactId(r["artifact_id"]),
        state=PipelineState(r["state"]),
        attempts=int(r["attempts"]),
        run_after=r["run_after"],
        locked_until=r["locked_until"],
        last_error=r["last_error"],
    )


class PipelineRepo:
    """Concrete asyncpg implementation of the PipelineRepo Protocol."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def claim_next(self) -> PipelineRow | None:
        """Atomically claim one ready row with SKIP LOCKED."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE pipeline SET
                  locked_until = now() + interval '10 minutes',
                  attempts = attempts + 1
                WHERE artifact_id = (
                  SELECT artifact_id FROM pipeline
                  WHERE state <> 'done' AND run_after <= now()
                    AND (locked_until IS NULL OR locked_until < now())
                  ORDER BY run_after
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1
                )
                RETURNING artifact_id, state, attempts, run_after, locked_until, last_error
                """
            )
        if row is None:
            return None
        return _row_from_record(row)

    async def advance(
        self,
        artifact_id: ArtifactId,
        *,
        from_state: PipelineState,
        outcome: StepOutcome,
        error: str | None = None,
    ) -> None:
        """Commit a transition."""
        new_state = outcome.next_state
        now = datetime.now(UTC)

        if outcome.park:
            await self._pool.execute(
                """
                UPDATE pipeline SET
                  state = $2::pipe_state,
                  locked_until = NULL,
                  last_error = $3,
                  updated_at = $4
                WHERE artifact_id = $1::uuid
                """,
                artifact_id,
                new_state.value,
                error,
                now,
            )
        elif new_state != from_state:
            await self._pool.execute(
                """
                UPDATE pipeline SET
                  state = $2::pipe_state,
                  locked_until = NULL,
                  last_error = NULL,
                  run_after = now(),
                  updated_at = $3
                WHERE artifact_id = $1::uuid
                """,
                artifact_id,
                new_state.value,
                now,
            )
        else:
            await self._pool.execute(
                """
                UPDATE pipeline SET
                  locked_until = NULL,
                  last_error = $3,
                  run_after = now() + interval '30 seconds',
                  updated_at = $4
                WHERE artifact_id = $1::uuid
                  AND state = $2::pipe_state
                """,
                artifact_id,
                from_state.value,
                error,
                now,
            )

    async def release(self, artifact_id: ArtifactId) -> None:
        """Release the lock on a row without advancing state."""
        await self._pool.execute(
            """
            UPDATE pipeline SET locked_until = NULL, updated_at = now()
            WHERE artifact_id = $1::uuid
            """,
            artifact_id,
        )
