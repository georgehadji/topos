"""Artifact ingestion and listing endpoints. Slice 0.12.

POST /artifacts/ingest — trigger a source fetch and push into pipeline
GET  /artifacts — list ingested artifacts
GET  /artifacts/{id} — get an artifact with its claims
"""

from __future__ import annotations

import hashlib
import uuid as uuid_mod
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from topos.adapters.sources.diavgeia import DiavgeiaConfig, DiavgeiaPlugin
from topos.config import get_settings
from topos.domain.types import ArtifactId

router = APIRouter(prefix="/artifacts")


async def get_pool() -> asyncpg.Pool:
    """Create a connection pool. For demo; in production use a shared pool."""
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.db_dsn, min_size=1, max_size=2)
    try:
        yield pool
    finally:
        await pool.close()


@router.post("/ingest")
async def ingest_artifacts(
    org: str = "",
    limit: int = 3,
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, object]:
    """Fetch decisions from Διαύγεια and push them into the pipeline."""
    plugin = DiavgeiaPlugin()
    config = DiavgeiaConfig(org=org, max_per_fetch=limit)
    count = 0

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO source (id, kind, config, cadence, rights)
            VALUES ('diavgeia', 'diavgeia', $1::jsonb, interval '1 hour', '{}'::jsonb)
            ON CONFLICT (id) DO UPDATE SET config = $1::jsonb
            """,
            config.model_dump_json(),
        )

        async for artifact in plugin.fetch(config):
            aid = ArtifactId(uuid_mod.uuid4())
            sha256 = hashlib.sha256(artifact.data).digest()

            await conn.execute(
                """
                INSERT INTO artifact
                  (id, source_id, uri, sha256, blob_key, mime, bytes, fetched_at)
                VALUES ($1::uuid, 'diavgeia', $2, $3::bytea, $1::text, $4, $5, now())
                ON CONFLICT (source_id, uri, sha256) DO NOTHING
                """,
                aid,
                artifact.uri,
                sha256,
                artifact.mime,
                len(artifact.data),
            )

            await conn.execute(
                """
                INSERT INTO pipeline (artifact_id, state)
                VALUES ($1::uuid, 'fetched'::pipe_state)
                ON CONFLICT (artifact_id) DO NOTHING
                """,
                aid,
            )
            count += 1

    return {"ingested": count}


@router.get("")
async def list_artifacts(
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> list[dict[str, object]]:
    """List all artifacts with their pipeline state."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id, a.uri, a.mime, a.bytes, a.fetched_at,
                   p.state AS pipeline_state
            FROM artifact a
            LEFT JOIN pipeline p ON p.artifact_id = a.id
            ORDER BY a.fetched_at DESC
            LIMIT 50
            """
        )
    return [dict(r) for r in rows]


@router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),  # noqa: B008
) -> dict[str, object]:
    """Get an artifact with its claims (if any)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT a.*, p.state AS pipeline_state
            FROM artifact a
            LEFT JOIN pipeline p ON p.artifact_id = a.id
            WHERE a.id = $1::uuid
            """,
            artifact_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Artifact not found")

        claims = await conn.fetch(
            "SELECT * FROM claim WHERE artifact_id = $1::uuid AND retracted_at IS NULL",
            artifact_id,
        )

    result = dict(row)
    result["claims"] = [dict(c) for c in claims]
    return result
