"""Unit tests: mention service claim/mention persistence.

Tests persist_extraction with a mock asyncpg pool.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.domain.extraction import (
    ClaimAtom,
    ExtractedChunk,
    ExtractedClaim,
    Extraction,
    Span,
)
from topos.service.mentions import persist_extraction


def _chunk(ord: int, text: str, predicates: list[str]) -> ExtractedChunk:
    return ExtractedChunk(
        ord=ord,
        text=text,
        claims=[
            ExtractedClaim(
                claim=ClaimAtom(predicate=p, value=f"value_{p}", confidence=None),
                span=Span(start=0, end=len(text)),
            )
            for p in predicates
        ],
    )


@pytest.mark.asyncio
async def test_persist_empty_extraction() -> None:
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    ext = Extraction(artifact_id="00000000-0000-0000-0000-000000000001", chunks=[])
    count = await persist_extraction(mock_pool, ext)
    assert count == 0
    assert mock_conn.execute.call_count == 0


@pytest.mark.asyncio
async def test_persist_one_claim() -> None:
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    ext = Extraction(
        artifact_id="00000000-0000-0000-0000-000000000001",
        chunks=[_chunk(0, "road has a pothole", ["road_damage"])],
    )
    count = await persist_extraction(mock_pool, ext)

    # 1 INSERT claim + 1 UPSERT problem + 1 INSERT problem_claim + 1 INSERT problem_event
    assert count == 1
    assert mock_conn.execute.call_count == 4


@pytest.mark.asyncio
async def test_persist_multiple_claims_same_chunk() -> None:
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    ext = Extraction(
        artifact_id="00000000-0000-0000-0000-000000000001",
        chunks=[
            _chunk(0, "water leak and broken pavement", ["water_leak", "road_damage"])
        ],
    )
    count = await persist_extraction(mock_pool, ext)
    assert count == 2
    # 2 claims → 2 x (1 claim INSERT + 1 problem UPSERT + 1 problem_claim + 1 event)
    assert mock_conn.execute.call_count == 8


@pytest.mark.asyncio
async def test_persist_multiple_chunks() -> None:
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    ext = Extraction(
        artifact_id="00000000-0000-0000-0000-000000000001",
        chunks=[
            _chunk(0, "chunk one", ["noise"]),
            _chunk(1, "chunk two", ["pollution"]),
        ],
    )
    count = await persist_extraction(mock_pool, ext)
    assert count == 2
    assert mock_conn.execute.call_count == 8
