"""Search and artifact HTTP endpoints for the React SPA.

Slice 1.12-1.14. Serves search results and provides the API backend
for the MapLibre-based React frontend.
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Query

from topos.adapters.db.search_repo import SearchRepo
from topos.config import get_settings
from topos.domain.search import SearchQuery
from topos.interfaces.rerank_factory import build_reranker

router = APIRouter(prefix="/api")


async def get_pool() -> asyncpg.Pool:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.db_dsn, min_size=1, max_size=2)
    try:
        yield pool
    finally:
        await pool.close()


@router.get("/search")
async def search(
    text: str = "",
    predicates: str | None = Query(default=None),
    limit: int = 20,
    offset: int = 0,
    rerank: bool = True,
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, object]:
    """Search mentions with FTS + optional filters, reranked (ADR-013)."""
    settings = get_settings()
    pred_list = predicates.split(",") if predicates else None
    query = SearchQuery(
        text=text,
        predicates=pred_list,
        limit=limit,
        offset=offset,
        rerank=rerank,
    )
    repo = SearchRepo(pool, build_reranker(settings), min_candidates=settings.rerank_candidates)
    response = await repo.search(query)
    return {
        "results": [
            {
                "problem_id": str(r.problem_id),
                "title": r.title,
                "category": r.category,
                "score": r.score,
                "snippet": r.snippet,
                "lat": r.lat,
                "lon": r.lon,
            }
            for r in response.results
        ],
        "total": response.total,
        "query": {"text": text, "limit": limit, "offset": offset},
    }
