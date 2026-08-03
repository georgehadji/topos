"""Export commands: dump problems and claims as NDJSON for Grok collections.

Usage::

    uv run topos-cli export problems --output problems.jsonl
    uv run topos-cli export claims --output claims.jsonl
    uv run topos-cli export all --output-dir ./exports
    uv run topos-cli export newsletter --output digest.md
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import typer

from topos.config import get_settings
from topos.interfaces.cli.io import emit
from topos.service.newsletter import build_newsletter

logger = logging.getLogger(__name__)

cli = typer.Typer(help="Export data for analyst Q&A collections.")


@cli.command()
def problems(
    output: str = "problems.jsonl",
    limit: int = 0,
    db_dsn: str | None = None,
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Export all non-retracted problems as NDJSON."""
    written = _run_export(
        output=output,
        limit=limit,
        db_dsn=db_dsn or get_settings().db_dsn,
        query=_PROBLEMS_QUERY,
        transform=_transform_problem,
        label="problems",
    )
    emit({"exported": "problems", "rows": written, "output": output}, as_json=json_out)


@cli.command()
def claims(
    output: str = "claims.jsonl",
    limit: int = 0,
    db_dsn: str | None = None,
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Export all non-retracted claims as NDJSON."""
    written = _run_export(
        output=output,
        limit=limit,
        db_dsn=db_dsn or get_settings().db_dsn,
        query=_CLAIMS_QUERY,
        transform=_transform_claim,
        label="claims",
    )
    emit({"exported": "claims", "rows": written, "output": output}, as_json=json_out)


@cli.command()
def all(
    output_dir: str = "./exports",
    limit: int = 0,
    db_dsn: str | None = None,
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Export both problems and claims to NDJSON files."""
    os.makedirs(output_dir, exist_ok=True)
    dsn = db_dsn or get_settings().db_dsn
    problems_path = os.path.join(output_dir, "problems.jsonl")
    claims_path = os.path.join(output_dir, "claims.jsonl")
    n_problems = _run_export(
        output=problems_path,
        limit=limit,
        db_dsn=dsn,
        query=_PROBLEMS_QUERY,
        transform=_transform_problem,
        label="problems",
    )
    n_claims = _run_export(
        output=claims_path,
        limit=limit,
        db_dsn=dsn,
        query=_CLAIMS_QUERY,
        transform=_transform_claim,
        label="claims",
    )
    emit(
        {
            "output_dir": output_dir,
            "problems": {"rows": n_problems, "output": problems_path},
            "claims": {"rows": n_claims, "output": claims_path},
        },
        as_json=json_out,
    )


@cli.command()
def newsletter(
    output: str = "newsletter.md",
    days: int = typer.Option(0, help="Only findings first seen in the last N days. 0 = all."),
    db_dsn: str | None = None,
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Render every finding as a dated Markdown digest."""
    since = datetime.now(UTC) - timedelta(days=days) if days > 0 else None
    dsn = db_dsn or get_settings().db_dsn

    async def _build() -> str:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        try:
            return await build_newsletter(pool, since=since)
        finally:
            await pool.close()

    markdown = asyncio.run(_build())
    with open(output, "w", encoding="utf-8") as f:
        f.write(markdown)
    logger.info("Wrote newsletter to %s", output)
    emit({"exported": "newsletter", "output": output, "bytes": len(markdown)}, as_json=json_out)


# ── Queries (PII-safe: exclude fields that could contain natural-person data) ─

_PROBLEMS_QUERY = """
SELECT
  id::text,
  title,
  category,
  status,
  ST_Y(geom) AS lat,
  ST_X(geom) AS lon,
  first_seen::text,
  last_seen::text,
  version
FROM problem
WHERE status <> 'retracted'
ORDER BY last_seen DESC
"""

_CLAIMS_QUERY = """
SELECT
  c.id::text,
  c.artifact_id::text,
  c.predicate,
  c.value::text,
  c.confidence::text,
  c.span::text
FROM claim c
WHERE c.retracted_at IS NULL
ORDER BY c.id
"""


def _transform_problem(row: dict[str, Any]) -> str:
    return json.dumps(
        {
            "problem_id": row["id"],
            "title": row["title"],
            "category": row["category"],
            "status": row["status"],
            "lat": row["lat"],
            "lon": row["lon"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "version": row["version"],
        },
        default=str,
        ensure_ascii=False,
    )


def _transform_claim(row: dict[str, Any]) -> str:
    return json.dumps(
        {
            "claim_id": row["id"],
            "artifact_id": row["artifact_id"],
            "predicate": row["predicate"],
            "value": row["value"],
            "confidence": row["confidence"],
            "span": row["span"],
        },
        default=str,
        ensure_ascii=False,
    )


def _run_export(
    *,
    output: str,
    limit: int,
    db_dsn: str,
    query: str,
    transform: Any,
    label: str,
) -> int:
    """Run query, collect rows synchronously, write NDJSON. Returns rows written."""

    async def _fetch() -> list[dict[str, Any]]:
        pool = await asyncpg.create_pool(db_dsn, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            sql = query
            if limit > 0:
                sql = f"{sql} LIMIT {limit}"
            rows = await conn.fetch(sql)
        await pool.close()
        return [dict(r) for r in rows]

    rows = asyncio.run(_fetch())
    with open(output, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(transform(row) + "\n")
    logger.info("Exported %d %s to %s", len(rows), label, output)
    return len(rows)


def main() -> None:
    cli()
