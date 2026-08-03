"""``topos-cli search`` — registered as a top-level command in main.py.

Kept out of main.py only for the 400-line file budget (same reasoning as
admin_cmd.py). Uses the same SearchRepo/SearchQuery as /api/search and the
search_problems MCP tool — one search implementation, reranked (ADR-013).
"""

from __future__ import annotations

import asyncio

import asyncpg
import typer

from topos.adapters.db.search_repo import SearchRepo
from topos.config import Settings, get_settings
from topos.domain.search import SearchQuery, SearchResponse
from topos.interfaces.cli.io import emit, fail
from topos.interfaces.rerank_factory import build_reranker


def search(
    text: str = typer.Argument("", help="Full-text query (Greek FTS + rerank)."),
    predicates: str = typer.Option("", help="Comma-separated category filter."),
    limit: int = typer.Option(20, help="Max results."),
    rerank: bool = typer.Option(True, help="Cross-encoder rerank the lexical hits."),
    db_dsn: str = typer.Option("", help="Override TOPOS_DB_DSN."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Search problems: Greek FTS lexical pass, optionally reranked."""
    settings = get_settings()
    dsn = db_dsn or settings.db_dsn
    query = SearchQuery(
        text=text,
        predicates=predicates.split(",") if predicates else None,
        limit=limit,
        rerank=rerank,
    )
    try:
        response = asyncio.run(_search(dsn, settings, query))
    except Exception as exc:
        fail(f"search failed: {type(exc).__name__}: {exc}", json_out=json_out)

    emit(
        {
            "total": response.total,
            "results": [
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
            ],
        },
        as_json=json_out,
    )


async def _search(dsn: str, settings: Settings, query: SearchQuery) -> SearchResponse:
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    if pool is None:  # pragma: no cover - asyncpg returns None only on bad config
        raise RuntimeError("could not create a connection pool")
    try:
        repo = SearchRepo(pool, build_reranker(settings), min_candidates=settings.rerank_candidates)
        return await repo.search(query)
    finally:
        await pool.close()
