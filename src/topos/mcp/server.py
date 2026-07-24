"""MCP server for Topos — exposes tools for LLM integration.

MCP (Model Context Protocol) allows LLM agents to query and act on
Topos data. This is a minimal stdio-based MCP server that provides:

Tools:
  - search_problems: search mentions with FTS + optional filters
  - get_artifact: retrieve artifact details with claims
  - approve_recommendation: sign off on a recommendation
"""

from __future__ import annotations

import json
from typing import Any

from topos.config import get_settings


async def _get_pool() -> Any:
    import asyncpg

    return await asyncpg.create_pool(get_settings().db_dsn, min_size=1, max_size=1)


async def handle_tool(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a tool call and return JSON result."""

    if name == "search_problems":
        pool = await _get_pool()
        try:
            from topos.adapters.db.search_repo import SearchRepo
            from topos.domain.search import SearchQuery

            repo = SearchRepo(pool)
            query = SearchQuery(
                text=arguments.get("text", ""),
                predicates=arguments.get("predicates"),
                lat=arguments.get("lat"),
                lon=arguments.get("lon"),
                radius_km=arguments.get("radius_km"),
                limit=arguments.get("limit", 10),
            )
            response = await repo.search(query)
            return json.dumps(
                [
                    {
                        "id": r.problem_id,
                        "title": r.title,
                        "category": r.category,
                        "score": r.score,
                        "lat": r.lat,
                        "lon": r.lon,
                    }
                    for r in response.results
                ]
            )
        finally:
            await pool.close()

    elif name == "get_artifact":
        pool = await _get_pool()
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT a.id::text, a.uri, a.mime, a.bytes, a.fetched_at,
                           p.state AS pipeline_state
                    FROM artifact a
                    LEFT JOIN pipeline p ON p.artifact_id = a.id
                    WHERE a.id = $1::uuid
                    """,
                    arguments["id"],
                )
                if row is None:
                    return json.dumps({"error": "not found"})
                return json.dumps(dict(row), default=str)
        finally:
            await pool.close()

    elif name == "approve_recommendation":
        pool = await _get_pool()
        try:
            from topos.service.recommendations import RecommendationService

            svc = RecommendationService(pool)
            await svc.approve(arguments["problem_id"], actor=arguments.get("actor", "mcp"))
            return json.dumps({"status": "approved"})
        finally:
            await pool.close()

    else:
        return json.dumps({"error": f"Unknown tool: {name}"})
