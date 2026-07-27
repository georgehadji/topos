"""Graph explorer HTTP endpoint.

Serves graph data for the React force-directed graph component.
"""

from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import APIRouter, Depends

from topos.adapters.db.graph_repo import GraphRepo
from topos.config import get_settings

router = APIRouter(prefix="/api/graph")


async def get_pool() -> asyncpg.Pool:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.db_dsn, min_size=1, max_size=2)
    try:
        yield pool
    finally:
        await pool.close()


@router.get("/problems")
async def get_graph(
    depth: int = 1,
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, Any]:
    """Get the full problem graph."""
    repo = GraphRepo(pool)
    result = await repo.problem_graph(depth=depth)
    return {
        "nodes": [
            {"id": n.id, "type": n.type, "label": n.label, "score": n.score} for n in result.nodes
        ],
        "edges": [
            {"source": e.source, "target": e.target, "relation": e.relation} for e in result.edges
        ],
    }


@router.get("/explore/{problem_id}")
async def explore_problem(
    problem_id: str,
    depth: int = 2,
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, Any]:
    """Traverse the graph from a single problem."""
    repo = GraphRepo(pool)
    result = await repo.explore(problem_id, depth=depth)
    return {
        "nodes": [
            {"id": n.id, "type": n.type, "label": n.label, "score": n.score} for n in result.nodes
        ],
        "edges": [
            {"source": e.source, "target": e.target, "relation": e.relation} for e in result.edges
        ],
    }
