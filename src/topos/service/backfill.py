"""Historical backfill pipeline.

Ingests a batch of documents from a source, runs them through the
full pipeline (fetch → textify → extract → mention), and records
cost and progress.

Run: uv run python -m topos.service.backfill --source diavgeia --limit 100
"""

from __future__ import annotations

import time
from typing import Any

import asyncpg

from topos.adapters.sources.diavgeia import DiavgeiaConfig, DiavgeiaPlugin
from topos.config import get_settings
from topos.domain.types import ArtifactId


async def backfill_source(
    pool: asyncpg.Pool,
    source_kind: str,
    *,
    max_pages: int = 10,
    page_size: int = 50,
    org: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backfill documents from a source.

    Returns a summary of ingested artifacts.
    """
    start = time.time()
    ingested = 0
    errors = 0

    if source_kind == "diavgeia":
        config = DiavgeiaConfig(max_per_fetch=page_size, org=org, max_pages=max_pages)
        plugin = DiavgeiaPlugin()
    else:
        return {"error": f"Unknown source: {source_kind}"}

    import hashlib
    import uuid

    async with pool.acquire() as conn:
        async for artifact in plugin.fetch(config):
            if dry_run:
                ingested += 1
                continue

            try:
                aid = ArtifactId(uuid.uuid4())
                sha256 = hashlib.sha256(artifact.data).digest()

                await conn.execute(
                    """
                    INSERT INTO artifact
                      (id, source_id, uri, sha256, blob_key, mime, bytes, fetched_at)
                    VALUES ($1::uuid, $2, $3, $4::bytea, $5, $6, $7, now())
                    ON CONFLICT (source_id, uri, sha256) DO NOTHING
                    """,
                    aid,
                    source_kind,
                    artifact.uri,
                    sha256,
                    str(aid),
                    artifact.mime or "application/octet-stream",
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

                ingested += 1
            except Exception:
                errors += 1

    elapsed = time.time() - start
    return {
        "source": source_kind,
        "ingested": ingested,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 2),
        "docs_per_second": round(ingested / elapsed, 2) if elapsed > 0 else 0,
        "dry_run": dry_run,
    }


async def main() -> None:
    """CLI entry point for backfill."""
    import argparse

    parser = argparse.ArgumentParser(description="Topos historical backfill")
    parser.add_argument("--source", default="diavgeia")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--org", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pool = await asyncpg.create_pool(get_settings().db_dsn, min_size=1, max_size=2)
    try:
        result = await backfill_source(
            pool,
            args.source,
            max_pages=args.limit // 50 + 1,
            org=args.org,
            dry_run=args.dry_run,
        )
        print(f"Backfill complete: {result}")
    finally:
        await pool.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
