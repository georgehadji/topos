"""GraphQL schema for Topos.

Provides a GraphQL endpoint for external tool integration (LLM agents,
custom dashboards, MCP server).

Queries:
  problems(search, status, limit) — list/search problems/mentions
  recommendations(status, limit) — ranked recommendations
  artifact(id) — single artifact with claims
"""

from __future__ import annotations

import strawberry
from strawberry.fastapi import GraphQLRouter


@strawberry.type
class ProblemGQL:
    id: str
    title: str
    category: str
    status: str
    priority: float | None
    lat: float | None
    lon: float | None


@strawberry.type
class RecommendationGQL:
    problem_id: str
    title: str
    category: str
    priority: float
    status: str
    approved_by: str | None


@strawberry.type
class Query:
    @strawberry.field
    async def problems(
        self,
        search: str = "",
        limit: int = 20,
    ) -> list[ProblemGQL]:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://localhost:8000/api/search",
                params={"text": search, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                ProblemGQL(
                    id=r["problem_id"],
                    title=r["title"],
                    category=r["category"],
                    status="candidate",
                    priority=r["score"],
                    lat=r["lat"],
                    lon=r["lon"],
                )
                for r in data.get("results", [])
            ]

    @strawberry.field
    async def recommendations(
        self,
        status: str | None = None,
        limit: int = 20,
    ) -> list[RecommendationGQL]:
        import asyncpg

        from topos.config import get_settings
        from topos.service.recommendations import RecommendationService

        pool = await asyncpg.create_pool(get_settings().db_dsn, min_size=1, max_size=1)
        try:
            svc = RecommendationService(pool)
            recs = await svc.list_recommendations(status=status, limit=limit)
            return [
                RecommendationGQL(
                    problem_id=r.problem_id,
                    title=r.title,
                    category=r.category,
                    priority=float(r.priority),
                    status=r.status,
                    approved_by=r.approved_by,
                )
                for r in recs
            ]
        finally:
            await pool.close()


schema = strawberry.Schema(query=Query)

# Mount in app.py with: app.include_router(GraphQLRouter(schema), prefix="/graphql")
graphql_router = GraphQLRouter(schema, prefix="")
