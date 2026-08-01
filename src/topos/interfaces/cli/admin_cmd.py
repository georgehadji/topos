"""Admin commands mounted at the top level of ``topos-cli``: ``seed``, ``cost``.

Kept out of ``main.py`` only for the 400-line file budget; these are registered
as top-level commands (``topos-cli seed``, ``topos-cli cost``) because the
Makefile and README document them that way.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import asyncpg
import typer

from topos.adapters.sources import registry
from topos.config import get_settings
from topos.interfaces.cli.io import emit, fail

# Per-source polling cadence. Anything not listed falls back to _DEFAULT_CADENCE.
_CADENCE: dict[str, str] = {
    "deddhe": "15 minutes",
    "news": "30 minutes",
    "social": "30 minutes",
    "municipality": "1 hour",
    "sonar_web": "6 hours",
    "diavgeia": "1 hour",
    "khmdhs": "6 hours",
    "fek": "12 hours",
}
_DEFAULT_CADENCE = "1 hour"

_RIGHTS: dict[str, Any] = {
    "license": "public-sector-information",
    "attribution_required": True,
    "store_full_text": True,
}

_SEED_SQL = """
INSERT INTO source (id, kind, config, cadence, rights, reliability, enabled)
-- $4 is cast text->interval so asyncpg binds a plain string rather than
-- demanding a datetime.timedelta for the interval parameter.
VALUES ($1, $2, $3::jsonb, $4::text::interval, $5::jsonb, $6, true)
ON CONFLICT (id) DO UPDATE
   SET kind = EXCLUDED.kind,
       config = EXCLUDED.config,
       cadence = EXCLUDED.cadence,
       rights = EXCLUDED.rights
"""

# Two static statements rather than one interpolated one — no SQL is ever built
# from user input.
_COST_CURRENT = """
SELECT coalesce(sum(cost_eur), 0)::float8      AS eur,
       count(*)                                AS runs,
       count(*) FILTER (WHERE NOT ok)          AS failed,
       coalesce(sum(tokens_in), 0)             AS tokens_in,
       coalesce(sum(tokens_out), 0)            AS tokens_out
FROM extraction_run
WHERE started_at >= date_trunc('month', now())
"""

_COST_MONTH = """
SELECT coalesce(sum(cost_eur), 0)::float8      AS eur,
       count(*)                                AS runs,
       count(*) FILTER (WHERE NOT ok)          AS failed,
       coalesce(sum(tokens_in), 0)             AS tokens_in,
       coalesce(sum(tokens_out), 0)            AS tokens_out
FROM extraction_run
WHERE started_at >= $1::date
  AND started_at <  ($1::date + interval '1 month')
"""


def seed(
    db_dsn: str = typer.Option("", help="Override TOPOS_DB_DSN."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Load the source registry into the `source` table (idempotent upsert).

    One row per plugin registered in ``adapters.sources``, seeded with that
    plugin's default config. Re-running refreshes config and cadence without
    touching `last_ok_at` / `last_error`.
    """
    dsn = db_dsn or get_settings().db_dsn
    try:
        seeded = asyncio.run(_seed(dsn))
    except Exception as exc:
        fail(f"seed failed: {type(exc).__name__}: {exc}", json_out=json_out)

    emit({"seeded": len(seeded), "sources": seeded}, as_json=json_out)


async def _seed(dsn: str) -> list[str]:
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        done: list[str] = []
        for kind in sorted(registry.list_kinds()):
            plugin_cls = registry.get(kind)
            if plugin_cls is None:  # pragma: no cover - list_kinds is the key set
                continue
            config = plugin_cls.config_model()
            await conn.execute(
                _SEED_SQL,
                kind,
                kind,
                config.model_dump_json(),
                _CADENCE.get(kind, _DEFAULT_CADENCE),
                json.dumps(_RIGHTS),
                0.50,
            )
            done.append(kind)
        return done
    finally:
        await conn.close()


def cost(
    month: str = typer.Option("current", help="'current' or an explicit YYYY-MM."),
    db_dsn: str = typer.Option("", help="Override TOPOS_DB_DSN."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Report LLM spend for a month, summed from `extraction_run`."""
    if month != "current" and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        fail(f"--month must be 'current' or YYYY-MM, got {month!r}", json_out=json_out)

    dsn = db_dsn or get_settings().db_dsn
    try:
        row = asyncio.run(_cost(dsn, month))
    except Exception as exc:
        fail(f"cost query failed: {type(exc).__name__}: {exc}", json_out=json_out)

    budget = get_settings().llm_monthly_budget_eur
    spent = float(row["eur"])
    emit(
        {
            "month": month,
            "eur": round(spent, 4),
            "budget_eur": budget,
            "budget_used_pct": round(100 * spent / budget, 2) if budget else None,
            "runs": row["runs"],
            "failed_runs": row["failed"],
            "tokens_in": row["tokens_in"],
            "tokens_out": row["tokens_out"],
        },
        as_json=json_out,
    )


async def _cost(dsn: str, month: str) -> asyncpg.Record:
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        if month == "current":
            row = await conn.fetchrow(_COST_CURRENT)
        else:
            row = await conn.fetchrow(_COST_MONTH, f"{month}-01")
        assert row is not None  # aggregate query always returns exactly one row
        return row
    finally:
        await conn.close()
