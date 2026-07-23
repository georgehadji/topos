"""Audit log writer: records user actions to the audit_log table.

Slice 1.11. Usage::

    from topos.adapters.db.audit import audit
    await audit(pool, "admin-user", "problem.merge", target_id="...")
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import asyncpg


async def audit(
    pool: asyncpg.Pool,
    actor: str,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Write one audit log entry."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO audit_log (actor, action, target_type, target_id, payload, ip, at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            """,
            actor,
            action,
            target_type,
            target_id,
            payload,
            ip,
            datetime.now(UTC),
        )
