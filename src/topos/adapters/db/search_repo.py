"""Search adapter: FTS + geo + filters via asyncpg.

Slice 1.10. Implements the search contract from domain/search.py.
Raw SQL — no ORM. Uses greek_cfg FTS config from migration 002.
"""

from __future__ import annotations

import asyncpg

from topos.domain.search import SearchQuery, SearchResponse, SearchResult


class SearchRepo:
    """Postgres search implementation."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search against the problem table.

        Lexical first pass via greek_cfg FTS, with optional geo filter.
        """
        conditions: list[str] = []
        params: list[object] = []
        param_idx = 0

        def next_param(value: object) -> str:
            nonlocal param_idx
            param_idx += 1
            params.append(value)
            return f"${param_idx}"

        if query.text:
            # FTS via plainto_tsquery for simple phrase matching
            tsquery = next_param(query.text)
            conditions.append(
                f"to_tsvector('greek_cfg', coalesce(p.title, ''))"
                f" @@ plainto_tsquery('greek_cfg', {tsquery})"
            )

        if query.predicates:
            pred_param = next_param(query.predicates)
            conditions.append(f"p.category = ANY({pred_param})")

        if query.lat is not None and query.lon is not None and query.radius_km is not None:
            lat_param = next_param(query.lat)
            lon_param = next_param(query.lon)
            radius_param = next_param(query.radius_km)
            # 6371 = earth radius in km. ST_DWithin uses meters.
            conditions.append(
                f"ST_DWithin(p.geom::geography, "
                f"ST_SetSRID(ST_MakePoint({lon_param}, {lat_param}), 4326)::geography,"
                f" {radius_param} * 1000)"
            )

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        sql = f"""
            SELECT p.id, p.title, p.category,
                   ST_X(p.geom) AS lon, ST_Y(p.geom) AS lat
            FROM problem p
            WHERE {where_clause}
            ORDER BY p.last_seen DESC
            LIMIT {next_param(query.limit)}
            OFFSET {next_param(query.offset)}
        """

        count_sql = f"""
            SELECT COUNT(*) FROM problem p WHERE {where_clause}
        """

        async with self._pool.acquire() as conn:
            total = await conn.fetchval(count_sql, *params[:param_idx])
            rows = await conn.fetch(sql, *params[:param_idx])

        results = [
            SearchResult(
                problem_id=str(r["id"]),
                title=r["title"],
                category=r["category"],
                score=1.0,
                lat=float(r["lat"]) if r["lat"] else None,
                lon=float(r["lon"]) if r["lon"] else None,
            )
            for r in rows
        ]

        return SearchResponse(results=results, total=total or 0, query=query)
