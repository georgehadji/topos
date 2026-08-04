"""Unit test: backfill re-ingesting an already-known artifact.

Regression for a real FK violation hit in dev: ON CONFLICT DO NOTHING drops
the row silently on a re-run, so the freshly generated id was never written —
the following pipeline insert then referenced a non-existent artifact_id.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.service.backfill import backfill_source


class _FakePlugin:
    def __init__(self, docs: list[Any]) -> None:
        self._docs = docs

    async def fetch(self, config: object) -> AsyncIterator[Any]:
        for doc in self._docs:
            yield doc


class _FakeArtifact:
    def __init__(self, uri: str) -> None:
        self.uri = uri
        self.data = b"content"
        self.mime = "application/pdf"


@pytest.mark.asyncio
async def test_reingest_uses_existing_artifact_id_not_the_freshly_generated_one() -> None:
    """The DB already has this artifact (ON CONFLICT fires); pipeline insert
    must use the id RETURNING gave back, not the discarded local uuid."""
    existing_id = uuid.uuid4()

    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=existing_id)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    result = await backfill_source(
        pool, "municipality", _FakePlugin([_FakeArtifact("municipality://a.pdf")]), config=None
    )

    assert result["errors"] == 0
    assert result["ingested"] == 1
    pipeline_call = next(
        c for c in conn.execute.call_args_list if "INSERT INTO pipeline" in c.args[0]
    )
    assert pipeline_call.args[1] == existing_id
