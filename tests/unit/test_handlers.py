"""Unit tests for pipeline state handlers.

Verifies that the handlers execute the correct database operations and trigger geocoding.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.adapters.geocode import geocode
from topos.domain.types import ArtifactId, PipelineRow, PipelineState
from topos.service.handlers import PipelineHandlers


@pytest.mark.asyncio
async def test_handle_fetched_inserts_document() -> None:
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Setup database mocks
    mock_conn.fetchval.return_value = None  # Document does not exist yet
    mock_conn.fetchrow.return_value = {
        "uri": "https://diavgeia.gov.gr/decision/123",
        "mime": "text/plain",
    }

    row = PipelineRow(
        artifact_id=ArtifactId(uuid.uuid4()),
        state=PipelineState.FETCHED,
        attempts=0,
        run_after=MagicMock(),
        locked_until=None,
        last_error=None,
    )

    handlers = PipelineHandlers(mock_pool, MagicMock(), geocode)
    await handlers.handle_fetched(row)

    # Asserts that SELECT and INSERT are called
    assert mock_conn.fetchval.call_count == 1
    assert mock_conn.fetchrow.call_count == 1
    assert mock_conn.execute.call_count == 1
    assert "document" in mock_conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_textified_inserts_chunk() -> None:
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Setup database mocks
    mock_conn.fetchval.side_effect = [
        None,  # Chunk 0 does not exist yet
        "Εγνατία 45, Θεσσαλονίκη",  # Document text
    ]

    row = PipelineRow(
        artifact_id=ArtifactId(uuid.uuid4()),
        state=PipelineState.TEXTIFIED,
        attempts=0,
        run_after=MagicMock(),
        locked_until=None,
        last_error=None,
    )

    handlers = PipelineHandlers(mock_pool, MagicMock(), geocode)
    await handlers.handle_textified(row)

    assert mock_conn.fetchval.call_count == 2
    assert mock_conn.execute.call_count == 1
    assert "chunk" in mock_conn.execute.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_extracted_triggers_geocoding() -> None:
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Mock claims
    mock_conn.fetch.side_effect = [
        [{"id": uuid.uuid4(), "value": "Εγνατία", "predicate": "water_leak"}],  # claims
        [{"problem_id": uuid.uuid4()}],  # problem IDs
    ]

    row = PipelineRow(
        artifact_id=ArtifactId(uuid.uuid4()),
        state=PipelineState.EXTRACTED,
        attempts=0,
        run_after=MagicMock(),
        locked_until=None,
        last_error=None,
    )

    handlers = PipelineHandlers(mock_pool, MagicMock(), geocode)
    await handlers.handle_extracted(row)

    # Should geocode 'Εγνατία' (which is in the in-memory gazetteer) and execute updates
    assert mock_conn.fetch.call_count == 2
    assert mock_conn.execute.call_count == 1
    assert "UPDATE problem" in mock_conn.execute.call_args[0][0]
