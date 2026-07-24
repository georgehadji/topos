"""Review task HTTP endpoints for the ER review queue.

Slice 2.8. Lists pending review tasks, allows claiming, resolving,
and reverting. Powers the Review UI in the React SPA.

Uses the review_task table created in migration 001_core.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from topos.config import get_settings

router = APIRouter(prefix="/api/review")


async def get_pool() -> asyncpg.Pool:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.db_dsn, min_size=1, max_size=2)
    try:
        yield pool
    finally:
        await pool.close()


@router.get("/tasks")
async def list_tasks(
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> list[dict[str, object]]:
    """List all unresolved review tasks, ordered by priority."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, kind, payload, priority, claimed_by, claimed_until, created_at
            FROM review_task
            WHERE resolved_at IS NULL
            ORDER BY priority, id
            LIMIT 100
            """
        )
    return [dict(r) for r in rows]


@router.post("/tasks")
async def create_review_task(
    kind: str,
    payload: dict[str, object],
    priority: int = 100,
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, object]:
    """Create a new review task (e.g. an uncertain ER merge)."""
    task_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO review_task (id, kind, payload, priority)
            VALUES ($1, $2, $3::jsonb, $4)
            """,
            task_id,
            kind,
            payload,
            priority,
        )
    return {"id": str(task_id), "kind": kind}


@router.post("/tasks/{task_id}/claim")
async def claim_task(
    task_id: uuid.UUID,
    actor: str = "anonymous",
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, object]:
    """Claim a review task (prevent other reviewers from picking it up)."""
    now = datetime.now(UTC)
    claimed_until = now.replace(hour=now.hour + 1)
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE review_task
            SET claimed_by = $2, claimed_until = $3
            WHERE id = $1 AND resolved_at IS NULL
              AND (claimed_by IS NULL OR claimed_until < now())
            """,
            task_id,
            actor,
            claimed_until,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=409, detail="Task already claimed or resolved")
    return {"id": str(task_id), "claimed_by": actor}


@router.post("/tasks/{task_id}/resolve")
async def resolve_task(
    task_id: uuid.UUID,
    resolution: dict[str, object] | None = None,
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, object]:
    """Resolve a review task (approve or reject an ER merge)."""
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE review_task
            SET resolved_at = $2, resolution = $3::jsonb
            WHERE id = $1 AND resolved_at IS NULL
            """,
            task_id,
            now,
            resolution,
        )
    return {"id": str(task_id), "resolved": True}
