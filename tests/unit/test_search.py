"""Unit tests: search query building.

Tests SearchRepo.search() with a mock pool to verify correct
SQL query construction and parameterisation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.adapters.db.search_repo import SearchRepo
from topos.domain.search import SearchQuery


def _mock_pool(fetchval_return: int = 0, fetch_return: list[str] | None = None) -> MagicMock:
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=fetchval_return)
    mock_conn.fetch = AsyncMock(return_value=fetch_return)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    return mock_pool


@pytest.mark.asyncio
async def test_search_empty_query() -> None:
    pool = _mock_pool(fetchval_return=0, fetch_return=[])
    repo = SearchRepo(pool)
    result = await repo.search(SearchQuery())
    assert result.total == 0
    assert result.results == []


@pytest.mark.asyncio
async def test_search_with_text_filter() -> None:
    pool = _mock_pool(fetchval_return=0, fetch_return=[])
    repo = SearchRepo(pool)
    await repo.search(SearchQuery(text="pothole"))

    # Verify the SQL contains an FTS condition
    sql = pool.acquire.return_value.__aenter__.return_value.fetch.call_args[0][0]
    assert "plainto_tsquery" in sql
    assert "greek_cfg" in sql
    # Verify parameter contains the search text
    params = pool.acquire.return_value.__aenter__.return_value.fetch.call_args[0][1:]
    assert any("pothole" in str(p) for p in params)


@pytest.mark.asyncio
async def test_search_with_predicate_filter() -> None:
    pool = _mock_pool(fetchval_return=0, fetch_return=[])
    repo = SearchRepo(pool)
    await repo.search(SearchQuery(predicates=["road_damage", "water_leak"]))

    sql = pool.acquire.return_value.__aenter__.return_value.fetch.call_args[0][0]
    assert "p.category = ANY(" in sql


@pytest.mark.asyncio
async def test_search_with_geo_filter() -> None:
    pool = _mock_pool(fetchval_return=0, fetch_return=[])
    repo = SearchRepo(pool)
    await repo.search(SearchQuery(lat=40.64, lon=22.94, radius_km=5.0))

    sql = pool.acquire.return_value.__aenter__.return_value.fetch.call_args[0][0]
    assert "ST_DWithin" in sql
    assert "ST_MakePoint" in sql


@pytest.mark.asyncio
async def test_search_with_all_filters() -> None:
    pool = _mock_pool(fetchval_return=0, fetch_return=[])
    repo = SearchRepo(pool)
    await repo.search(
        SearchQuery(
            text="water",
            predicates=["water_leak"],
            lat=40.64,
            lon=22.94,
            radius_km=10.0,
            limit=5,
        )
    )

    sql = pool.acquire.return_value.__aenter__.return_value.fetch.call_args[0][0]
    assert all(keyword in sql for keyword in ["plainto_tsquery", "ANY(", "ST_DWithin", "LIMIT"])
