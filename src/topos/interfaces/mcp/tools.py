"""MCP tool definitions and handlers — read-only access to Topos data.

Each tool is a pure database query handler registered with the MCP protocol
handler via the ``@register_tool`` decorator. All tools are read-only.
No write operations are exposed (write-back requires a future ADR).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from topos.adapters.db.search_repo import SearchRepo
from topos.config import get_settings
from topos.domain.search import SearchQuery
from topos.interfaces.mcp import register_tool
from topos.interfaces.rerank_factory import build_reranker

logger = logging.getLogger(__name__)


async def _get_pool() -> asyncpg.Pool:
    """Create a short-lived connection pool for a tool invocation."""
    s = get_settings()
    return await asyncpg.create_pool(s.db_dsn, min_size=1, max_size=2)


# ── Tool: search_problems ────────────────────────────────────────────────────


@register_tool(
    name="search_problems",
    description=(
        "Search citizen-reported problems by text query, category predicate, "
        "and/or geographic radius. Returns problem_id, title, category, "
        "priority score, and location."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Full-text search over problem titles"},
            "predicates": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Category filter, e.g. road_damage, water_leak",
            },
            "lat": {"type": "number", "description": "Center latitude for radius search"},
            "lon": {"type": "number", "description": "Center longitude for radius search"},
            "radius_km": {"type": "number", "description": "Search radius in km"},
            "limit": {"type": "integer", "description": "Max results (default 20)"},
        },
    },
)
async def search_problems(args: dict[str, Any]) -> list[dict[str, Any]]:
    """Search problems by text, predicates, and/or location.

    Delegates to the same SearchRepo/SearchQuery as /api/search — this tool
    used to carry its own independent SQL, which had drifted into three real
    bugs: ST_DWithin compared bare geometry against a metres radius with no
    ::geography cast (SRID mismatch — PostGIS errors on that), ST_X/ST_Y
    were swapped, and the status filter checked for a 'retracted' value that
    was never in the ProblemStatus enum. One search implementation, not two
    that silently diverge, also means this tool gets reranking (ADR-013)
    for free.
    """
    settings = get_settings()
    pool = await _get_pool()
    try:
        repo = SearchRepo(pool, build_reranker(settings), min_candidates=settings.rerank_candidates)
        response = await repo.search(
            SearchQuery(
                text=args.get("query", ""),
                predicates=args.get("predicates") or None,
                lat=args.get("lat"),
                lon=args.get("lon"),
                radius_km=args.get("radius_km"),
                limit=min(args.get("limit", 20), 100),
            )
        )
        return [
            {
                "problem_id": r.problem_id,
                "title": r.title,
                "category": r.category,
                "score": r.score,
                "snippet": r.snippet,
                "lat": r.lat,
                "lon": r.lon,
            }
            for r in response.results
        ]
    finally:
        await pool.close()


# ── Tool: get_problem_detail ─────────────────────────────────────────────────


@register_tool(
    name="get_problem_detail",
    description=(
        "Get full details for a specific problem, including its claims, "
        "events, geolocation, and authority assignment."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "problem_id": {
                "type": "string",
                "description": "UUID of the problem to retrieve",
            },
        },
        "required": ["problem_id"],
    },
)
async def get_problem_detail(args: dict[str, Any]) -> dict[str, Any]:
    """Get full problem detail with claims and events."""
    problem_id = args.get("problem_id", "")

    pool = await _get_pool()
    try:
        async with pool.acquire() as conn:
            # Problem. ST_X is longitude, ST_Y is latitude for a
            # geometry(Point, 4326) — this previously had the aliases
            # swapped (same bug service/er.py had; search_repo.py always
            # had it right). authority_id/name were never selected despite
            # this tool's own description promising "authority assignment".
            row = await conn.fetchrow(
                """
                SELECT
                    p.id::text, p.title, p.category, p.status,
                    ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon,
                    p.first_seen, p.last_seen, p.version,
                    a.id::text AS authority_id, a.name AS authority_name
                FROM problem p
                LEFT JOIN authority a ON a.id = p.authority_id
                WHERE p.id = $1::uuid
                """,
                problem_id,
            )
            if row is None:
                return {"error": f"Problem not found: {problem_id}"}

            # Claims
            claims_rows = await conn.fetch(
                """
                SELECT c.id::text, c.predicate, c.value::text, c.confidence::text
                FROM claim c
                JOIN problem_claim pc ON pc.claim_id = c.id
                WHERE pc.problem_id = $1::uuid AND c.retracted_at IS NULL
                """,
                problem_id,
            )

            # Events
            events_rows = await conn.fetch(
                """
                SELECT seq, kind, payload::text, actor, at::text
                FROM problem_event
                WHERE problem_id = $1::uuid
                ORDER BY seq
                """,
                problem_id,
            )

        return {
            "problem_id": str(row["id"]),
            "title": row["title"],
            "category": row["category"],
            "status": row["status"],
            "lat": float(row["lat"]) if row["lat"] else None,
            "lon": float(row["lon"]) if row["lon"] else None,
            "first_seen": str(row["first_seen"]),
            "last_seen": str(row["last_seen"]),
            "version": row["version"],
            "authority_id": row["authority_id"],
            "authority_name": row["authority_name"],
            "claims": [
                {
                    "claim_id": str(r["id"]),
                    "predicate": r["predicate"],
                    "value": r["value"],
                    "confidence": r["confidence"],
                }
                for r in claims_rows
            ],
            "events": [
                {
                    "seq": r["seq"],
                    "kind": r["kind"],
                    "payload": r["payload"],
                    "actor": r["actor"],
                    "at": r["at"],
                }
                for r in events_rows
            ],
        }
    finally:
        await pool.close()


# ── Tool: get_pipeline_status ────────────────────────────────────────────────


@register_tool(
    name="get_pipeline_status",
    description="Get the current pipeline processing status — counts by state.",
    input_schema={
        "type": "object",
        "properties": {},
    },
)
async def get_pipeline_status(args: dict[str, Any]) -> dict[str, Any]:
    """Get pipeline status summary."""
    pool = await _get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT state, COUNT(*) AS cnt
                FROM pipeline
                GROUP BY state
                ORDER BY state
                """
            )
            total = sum(r["cnt"] for r in rows)
            by_state = {r["state"]: r["cnt"] for r in rows}
        return {"total": total, "by_state": by_state}
    finally:
        await pool.close()


# ── Tool: list_sources ────────────────────────────────────────────────────────


@register_tool(
    name="list_sources",
    description="List all registered data sources and their status.",
    input_schema={
        "type": "object",
        "properties": {},
    },
)
async def list_sources(args: dict[str, Any]) -> list[dict[str, Any]]:
    """List all registered sources."""
    pool = await _get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id::text, kind, cadence, enabled, reliability::float8 AS reliability,
                       last_ok_at::text, last_error, rights::text
                FROM source
                ORDER BY kind
                """
            )
        return [
            {
                "id": str(r["id"]),
                "kind": r["kind"],
                "cadence": str(r["cadence"]) if r["cadence"] else None,
                "enabled": r["enabled"],
                "reliability": r["reliability"],
                "last_ok_at": r["last_ok_at"],
                "last_error": r["last_error"],
                "rights": r["rights"],
            }
            for r in rows
        ]
    finally:
        await pool.close()


# ── Tool: get_scoring_breakdown ──────────────────────────────────────────────


@register_tool(
    name="get_scoring_breakdown",
    description=(
        "Get the full scoring breakdown for a problem — impact, urgency, "
        "priority, severity, reach, trend, evidence strength, tractability, "
        "cost, and leverage."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "problem_id": {
                "type": "string",
                "description": "UUID of the problem",
            },
        },
        "required": ["problem_id"],
    },
)
async def get_scoring_breakdown(args: dict[str, Any]) -> dict[str, Any]:
    """Get the latest score snapshot for a problem."""
    problem_id = args.get("problem_id", "")
    pool = await _get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                -- The scorecard lives in one jsonb column, keyed by the
                -- domain.scoring.ScoreSnapshot field names (001_core).
                SELECT scores::text AS scores, at::text AS at, formula_ver
                FROM score_snapshot
                WHERE problem_id = $1::uuid
                ORDER BY at DESC
                LIMIT 1
                """,
                problem_id,
            )
        if row is None:
            return {"error": f"No scoring data for problem: {problem_id}", "problem_id": problem_id}
        scores: dict[str, Any] = json.loads(row["scores"])
        numeric = (
            "impact",
            "urgency",
            "priority",
            "severity",
            "trend",
            "evidence_strength",
            "tractability",
            "cost_eur",
            "leverage",
        )
        result: dict[str, Any] = {"problem_id": problem_id}
        for key in numeric:
            value = scores.get(key)
            result[key] = float(value) if value is not None else None
        result["reach"] = scores.get("reach")
        result["computed_at"] = row["at"]
        result["formula_version"] = row["formula_ver"]
        return result
    finally:
        await pool.close()
