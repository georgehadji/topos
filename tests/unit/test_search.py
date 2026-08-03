"""Unit tests: search query building.

Tests SearchRepo.search() with a mock pool to verify correct
SQL query construction and parameterisation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.adapters.db.search_repo import SearchRepo
from topos.domain.search import SearchQuery


def _row(id_: str, title: str, category: str, score: float, snippet: str) -> dict[str, object]:
    return {
        "id": id_,
        "title": title,
        "category": category,
        "score": score,
        "snippet": snippet,
        "lat": None,
        "lon": None,
    }


def _mock_pool(fetchval_return: int = 0, fetch_return: list[Any] | None = None) -> MagicMock:
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


# ── Reranking (ADR-013) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_reranker_injected_keeps_lexical_order() -> None:
    """Default construction (no reranker arg) must behave exactly as before —
    this is the fail-open path when rerank is unconfigured, not just on error."""
    rows = [_row("1", "A", "cat", 0.9, "a"), _row("2", "B", "cat", 0.5, "b")]
    pool = _mock_pool(fetchval_return=2, fetch_return=rows)
    repo = SearchRepo(pool)

    result = await repo.search(SearchQuery(text="x", limit=2))

    assert [r.problem_id for r in result.results] == ["1", "2"]


@pytest.mark.asyncio
async def test_rerank_reorders_results() -> None:
    rows = [_row("1", "Pothole", "road_damage", 0.9, "pothole snippet")]
    rows.append(_row("2", "Water leak", "water_leak", 0.5, "water leak snippet"))
    pool = _mock_pool(fetchval_return=2, fetch_return=rows)

    async def fake_reranker(query: str, documents: list[str], *, top_n: int) -> Any:
        return [(1, 0.99), (0, 0.10)]  # reverse the lexical order

    repo = SearchRepo(pool, fake_reranker, min_candidates=10)
    result = await repo.search(SearchQuery(text="water leak", limit=2))

    assert [r.problem_id for r in result.results] == ["2", "1"]


@pytest.mark.asyncio
async def test_rerank_failure_falls_back_to_lexical_order() -> None:
    rows = [_row("1", "A", "cat", 0.9, "a"), _row("2", "B", "cat", 0.5, "b")]
    pool = _mock_pool(fetchval_return=2, fetch_return=rows)

    async def broken_reranker(query: str, documents: list[str], *, top_n: int) -> Any:
        raise RuntimeError("vendor down")

    repo = SearchRepo(pool, broken_reranker, min_candidates=10)
    result = await repo.search(SearchQuery(text="x", limit=2))

    assert [r.problem_id for r in result.results] == ["1", "2"]


@pytest.mark.asyncio
async def test_rerank_false_skips_reranker_even_when_injected() -> None:
    rows = [_row("1", "A", "cat", 0.9, "a")]
    pool = _mock_pool(fetchval_return=1, fetch_return=rows)
    called = False

    async def spy_reranker(query: str, documents: list[str], *, top_n: int) -> Any:
        nonlocal called
        called = True
        return []

    repo = SearchRepo(pool, spy_reranker)
    await repo.search(SearchQuery(text="x", rerank=False))

    assert called is False


@pytest.mark.asyncio
async def test_rerank_overfetches_candidate_window() -> None:
    pool = _mock_pool(fetchval_return=0, fetch_return=[])

    async def fake_reranker(query: str, documents: list[str], *, top_n: int) -> Any:
        return []

    repo = SearchRepo(pool, fake_reranker, min_candidates=50)
    await repo.search(SearchQuery(text="x", limit=5, offset=0))

    params = pool.acquire.return_value.__aenter__.return_value.fetch.call_args[0][1:]
    # LIMIT param is max(offset+limit, min_candidates) = 50, not the page size 5.
    assert 50 in params
    assert 5 not in params


@pytest.mark.asyncio
async def test_no_text_query_never_reranks() -> None:
    """Nothing to send a cross-encoder without a query string."""
    pool = _mock_pool(fetchval_return=0, fetch_return=[])
    called = False

    async def spy_reranker(query: str, documents: list[str], *, top_n: int) -> Any:
        nonlocal called
        called = True
        return []

    repo = SearchRepo(pool, spy_reranker)
    await repo.search(SearchQuery(predicates=["road_damage"]))

    assert called is False
