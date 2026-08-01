"""Unit tests for pipeline state handlers.

Verifies that the handlers execute the correct database operations and trigger geocoding.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.adapters.geocode import geocode
from topos.adapters.ocr import extract_text
from topos.domain.types import ArtifactId, PipelineRow, PipelineState
from topos.service.handlers import PipelineHandlers

_GREEK = "Απόφαση Δήμου Θεσσαλονίκης: βλάβη στον αγωγό ύδρευσης επί της οδού Εγνατία."


def _blob(data: bytes = b"") -> MagicMock:
    """A BlobReader whose get() returns *data*."""
    blob = MagicMock()
    blob.get = AsyncMock(return_value=data)
    return blob


@pytest.mark.asyncio
async def test_handle_fetched_stores_the_real_fetched_bytes() -> None:
    """The document text must come from the blob, not be inferred from the URI."""
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.return_value = None  # Document does not exist yet
    mock_conn.fetchrow.return_value = {
        "uri": "https://diavgeia.gov.gr/decision/123",
        "mime": "text/plain",
        "blob_key": "deadbeef",
    }

    row = PipelineRow(
        artifact_id=ArtifactId(uuid.uuid4()),
        state=PipelineState.FETCHED,
        attempts=0,
        run_after=MagicMock(),
        locked_until=None,
        last_error=None,
    )

    blob = _blob(_GREEK.encode("utf-8"))
    handlers = PipelineHandlers(mock_pool, MagicMock(), geocode, blob, extract_text)
    await handlers.handle_fetched(row)

    blob.get.assert_awaited_once_with("deadbeef")
    assert mock_conn.execute.call_count == 1
    args = mock_conn.execute.call_args[0]
    assert "document" in args[0]
    assert args[2] == _GREEK  # stored text is exactly what was fetched
    assert args[3] == "native"


@pytest.mark.asyncio
async def test_handle_fetched_parks_unreadable_bytes_instead_of_inventing_text() -> None:
    """A scan has no text layer. It must raise, never fall back to a stub."""
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.return_value = None
    mock_conn.fetchrow.return_value = {
        "uri": "https://diavgeia.gov.gr/decision/scan",
        "mime": "application/pdf",
        "blob_key": "deadbeef",
    }

    row = PipelineRow(
        artifact_id=ArtifactId(uuid.uuid4()),
        state=PipelineState.FETCHED,
        attempts=0,
        run_after=MagicMock(),
        locked_until=None,
        last_error=None,
    )

    handlers = PipelineHandlers(
        mock_pool, MagicMock(), geocode, _blob(b"%PDF-1.4 not really a pdf"), extract_text
    )

    with pytest.raises(ValueError, match="no_text_layer"):
        await handlers.handle_fetched(row)

    mock_conn.execute.assert_not_called()


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

    handlers = PipelineHandlers(mock_pool, MagicMock(), geocode, _blob(), extract_text)
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

    handlers = PipelineHandlers(mock_pool, MagicMock(), geocode, _blob(), extract_text)
    await handlers.handle_extracted(row)

    # Should geocode 'Εγνατία' (which is in the in-memory gazetteer) and execute updates
    assert mock_conn.fetch.call_count == 2
    assert mock_conn.execute.call_count == 1
    assert "UPDATE problem" in mock_conn.execute.call_args[0][0]
