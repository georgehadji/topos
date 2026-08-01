"""Search adapter: FTS + geo + filters via asyncpg.

Slice 1.10. Implements the search contract from domain/search.py.
Raw SQL — no ORM. Uses the greek_cfg FTS config (migration 002, restemmed in 006).

Text matching runs against `chunk.tsv` — the stored, GIN-indexed tsvector over
document body text — reached from a problem through problem_claim -> claim ->
chunk. Problem titles are matched too, but a title is one short line; the body
is where the Greek actually lives.
"""

from __future__ import annotations

import asyncpg

from topos.domain.search import SearchQuery, SearchResponse, SearchResult

# One fragment, long enough to read, short enough for a result list.
_HEADLINE_OPTS = "MaxFragments=1,MaxWords=20,MinWords=5,StartSel=<b>,StopSel=</b>"


class SearchRepo:
    """Postgres search implementation."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search against the problem table.

        Lexical first pass via greek_cfg over chunk.tsv, with optional geo filter.
        """
        conditions: list[str] = []
        params: list[object] = []
        param_idx = 0

        def next_param(value: object) -> str:
            nonlocal param_idx
            param_idx += 1
            params.append(value)
            return f"${param_idx}"

        # The best-matching chunk per problem, if any. LEFT JOIN so that a
        # title-only hit still returns the row (with no snippet).
        join_clause = ""
        score_expr = "1.0"
        snippet_expr = "''"
        order_by = "p.last_seen DESC"

        if query.text:
            tsq = f"plainto_tsquery('greek_cfg', {next_param(query.text)})"
            join_clause = f"""
            LEFT JOIN LATERAL (
                SELECT ts_rank(ch.tsv, {tsq}) AS score,
                       ts_headline('greek_cfg', ch.text, {tsq}, '{_HEADLINE_OPTS}') AS snippet
                FROM problem_claim pc
                JOIN claim c  ON c.id = pc.claim_id
                JOIN chunk ch ON ch.artifact_id = c.artifact_id
                WHERE pc.problem_id = p.id
                  AND ch.tsv @@ {tsq}
                ORDER BY score DESC
                LIMIT 1
            ) m ON TRUE
            """
            conditions.append(
                f"(m.score IS NOT NULL OR to_tsvector('greek_cfg', coalesce(p.title, '')) @@ {tsq})"
            )
            score_expr = "COALESCE(m.score, 0)"
            snippet_expr = "COALESCE(m.snippet, '')"
            order_by = "score DESC, p.last_seen DESC"

        if query.predicates:
            pred_param = next_param(query.predicates)
            conditions.append(f"p.category = ANY({pred_param})")

        if query.lat is not None and query.lon is not None and query.radius_km is not None:
            lat_param = next_param(query.lat)
            lon_param = next_param(query.lon)
            radius_param = next_param(query.radius_km)
            # ST_DWithin on geography works in metres; radius_km is km.
            conditions.append(
                f"ST_DWithin(p.geom::geography, "
                f"ST_SetSRID(ST_MakePoint({lon_param}, {lat_param}), 4326)::geography,"
                f" {radius_param} * 1000)"
            )

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        where_params = list(params)

        sql = f"""
            SELECT p.id, p.title, p.category,
                   ST_X(p.geom) AS lon, ST_Y(p.geom) AS lat,
                   {score_expr} AS score,
                   {snippet_expr} AS snippet
            FROM problem p
            {join_clause}
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT {next_param(query.limit)}
            OFFSET {next_param(query.offset)}
        """

        count_sql = f"""
            SELECT COUNT(*)
            FROM problem p
            {join_clause}
            WHERE {where_clause}
        """

        async with self._pool.acquire() as conn:
            total = await conn.fetchval(count_sql, *where_params)
            rows = await conn.fetch(sql, *params)

        results = [
            SearchResult(
                problem_id=str(r["id"]),
                title=r["title"],
                category=r["category"],
                score=float(r["score"]),
                snippet=r["snippet"] or "",
                lat=float(r["lat"]) if r["lat"] is not None else None,
                lon=float(r["lon"]) if r["lon"] is not None else None,
            )
            for r in rows
        ]

        return SearchResponse(results=results, total=total or 0, query=query)
