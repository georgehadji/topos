"""Recommendation service: approval gate + export.

Slice 3.2. Manages the recommendation lifecycle:
  pending → approved → exported
  pending → rejected (blocked)

Every write is audited (ARCHITECTURE.md L6).
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

from topos.domain.recommendations import Recommendation


class RecommendationService:
    """Manages recommendation lifecycle."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_recommendations(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Recommendation]:
        """List all recommendations, optionally filtered by status."""
        conditions = ["1=1"]
        params: list[object] = []

        if status:
            conditions.append(f"p.status = ${len(params) + 1}")
            params.append(status)

        # NB: the S608 exemption for this f-string lives in pyproject's
        # per-file-ignores. It must not go inside the quotes — Postgres would
        # receive the `#` as SQL.
        sql = f"""
            SELECT p.id::text, p.title, p.category,
                   COALESCE(s.priority, 0) AS priority,
                   s.impact, s.urgency,
                   '' AS explanation,
                   p.status,
                   p.approved_by, p.approved_at, p.exported_at
            FROM problem p
            LEFT JOIN LATERAL (
              -- score_snapshot keeps the whole scorecard in one jsonb column
              -- (001_core); these are not flat columns.
              SELECT (scores->>'priority')::numeric AS priority,
                     (scores->>'impact')::numeric   AS impact,
                     (scores->>'urgency')::numeric  AS urgency
              FROM score_snapshot
              WHERE problem_id = p.id
              ORDER BY at DESC
              LIMIT 1
            ) s ON TRUE
            WHERE {" AND ".join(conditions)}
            ORDER BY priority DESC NULLS LAST
            LIMIT ${len(params) + 1}
        """
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [
            Recommendation(
                problem_id=r["id"],
                title=r["title"],
                category=r["category"],
                priority=r["priority"],
                impact=r["impact"],
                urgency=r["urgency"],
                explanation="",
                status=r["status"] or "candidate",
                approved_by=r.get("approved_by"),
                approved_at=r.get("approved_at"),
                exported_at=r.get("exported_at"),
            )
            for r in rows
        ]

    async def approve(
        self,
        problem_id: str,
        actor: str,
    ) -> None:
        """Approve a recommendation (human sign-off)."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE problem
                SET status = 'tracked',
                    approved_by = $2,
                    approved_at = $3
                WHERE id = $1::uuid AND status = 'candidate'
                """,
                problem_id,
                actor,
                now,
            )

    async def reject(self, problem_id: str, actor: str, reason: str = "") -> None:
        """Reject a recommendation."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE problem
                SET status = 'resolved',
                    approved_by = $2,
                    approved_at = $3
                WHERE id = $1::uuid AND status = 'candidate'
                """,
                problem_id,
                actor,
                now,
            )

    async def export(self, problem_id: str, actor: str) -> dict[str, object] | None:
        """Mark a recommendation as exported and return its data.

        Only approved recommendations can be exported (L6).
        """
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE problem
                SET status = 'acted_upon',
                    exported_at = $2
                WHERE id = $1::uuid AND status = 'tracked'
                RETURNING id::text, title, category, approved_by, approved_at
                """,
                problem_id,
                now,
            )
            if row is None:
                return None
            return dict(row)
