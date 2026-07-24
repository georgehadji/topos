"""Recommendation engine HTTP endpoints.

GET  /api/recommendations — ranked list
POST /api/recommendations/{id}/approve — human sign-off (L6)
POST /api/recommendations/{id}/reject — block
POST /api/recommendations/{id}/export — export approved recommendation
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from topos.config import get_settings
from topos.service.recommendations import RecommendationService

router = APIRouter(prefix="/api/recommendations")


async def get_pool() -> asyncpg.Pool:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.db_dsn, min_size=1, max_size=2)
    try:
        yield pool
    finally:
        await pool.close()


@router.get("")
async def list_recommendations(
    status: str | None = None,
    limit: int = 50,
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> list[dict[str, object]]:
    """List recommendations, ranked by priority."""
    svc = RecommendationService(pool)
    recs = await svc.list_recommendations(status=status, limit=limit)
    return [
        {
            "problem_id": r.problem_id,
            "title": r.title,
            "category": r.category,
            "priority": float(r.priority),
            "impact": float(r.impact) if r.impact else None,
            "urgency": float(r.urgency) if r.urgency else None,
            "status": r.status,
            "approved_by": r.approved_by,
            "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        }
        for r in recs
    ]


@router.post("/{problem_id}/approve")
async def approve_recommendation(
    problem_id: str,
    actor: str = "admin",
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, object]:
    """Approve a recommendation (human sign-off, L6)."""
    svc = RecommendationService(pool)
    await svc.approve(problem_id, actor)
    return {"problem_id": problem_id, "status": "approved"}


@router.post("/{problem_id}/reject")
async def reject_recommendation(
    problem_id: str,
    actor: str = "admin",
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, object]:
    """Reject a recommendation."""
    svc = RecommendationService(pool)
    await svc.reject(problem_id, actor)
    return {"problem_id": problem_id, "status": "rejected"}


@router.post("/{problem_id}/export")
async def export_recommendation(
    problem_id: str,
    actor: str = "admin",
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, object]:
    """Export a signed-off recommendation."""
    svc = RecommendationService(pool)
    result = await svc.export(problem_id, actor)
    if result is None:
        raise HTTPException(
            status_code=409,
            detail="Recommendation not approved or not found",
        )
    return result
