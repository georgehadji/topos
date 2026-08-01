"""Historical backfill pipeline.

Ingests a batch of documents from a source and enqueues them at the head of
the pipeline (``fetched``), where the worker picks them up and drives them
through textify -> extract -> geocode -> mention.

The concrete source plugin is resolved by interfaces/ (see
``topos.interfaces.cli.main``) and injected — service/ never imports
``adapters.sources`` (.importlinter contract ``service-ports-only``).

Run: uv run topos-cli backfill --source diavgeia --limit 100
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any

import asyncpg

from topos.domain.types import ArtifactId
from topos.service.ports import BlobStore, SourcePlugin

logger = logging.getLogger(__name__)


async def backfill_source(
    pool: asyncpg.Pool,
    source_kind: str,
    plugin: SourcePlugin,
    config: Any,
    *,
    blob: BlobStore | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backfill documents from *plugin* into the artifact + pipeline tables.

    *source_kind* is the registry key (e.g. ``"diavgeia"``); it is written to
    ``artifact.source_id``.

    *blob* stores the fetched bytes, and is what makes the rest of the pipeline
    possible: ``handle_fetched`` reads them back to produce the document text.
    Without it the payload is discarded and every artifact parks as unreadable.

    Returns a summary of what was ingested.
    """
    start = time.time()
    ingested = 0
    errors = 0
    stored = 0

    async with pool.acquire() as conn:
        async for artifact in plugin.fetch(config):
            if dry_run:
                ingested += 1
                continue

            try:
                aid = ArtifactId(uuid.uuid4())
                sha256 = hashlib.sha256(artifact.data).digest()

                # Content-addressed: the key is the sha256 of the bytes, so the
                # same document fetched twice occupies one object.
                blob_key = sha256.hex()
                if blob is not None:
                    blob_key = await blob.put(
                        blob_key,
                        artifact.data,
                        content_type=artifact.mime or "application/octet-stream",
                    )
                    stored += 1

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
                    blob_key,
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
                # One bad artifact must not abort the whole backfill, but it
                # must never be swallowed silently either.
                errors += 1
                logger.exception("backfill.artifact_failed uri=%s", artifact.uri)

    elapsed = time.time() - start
    return {
        "source": source_kind,
        "ingested": ingested,
        "stored_blobs": stored,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 2),
        "docs_per_second": round(ingested / elapsed, 2) if elapsed > 0 else 0,
        "dry_run": dry_run,
    }
