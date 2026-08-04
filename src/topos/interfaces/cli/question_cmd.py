"""``topos-cli question`` — draft a parliamentary question for a problem.

Kept out of main.py for the file-size budget, same as search_cmd/export_cmd.
"""

from __future__ import annotations

import asyncio

import asyncpg
import typer

from topos.config import get_settings
from topos.interfaces.cli.io import emit
from topos.service.questions import draft_for_problem


def question_cmd(
    problem_id: str = typer.Argument(..., help="Problem UUID to draft for."),
    output: str = typer.Option("", help="Write to this file instead of stdout."),
    db_dsn: str | None = None,
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Draft a written parliamentary question grounded in stored claims."""
    dsn = db_dsn or get_settings().db_dsn

    async def _draft() -> str | None:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        try:
            return await draft_for_problem(pool, problem_id)
        finally:
            await pool.close()

    draft = asyncio.run(_draft())
    if draft is None:
        emit({"ok": False, "error": f"no problem {problem_id}"}, as_json=json_out)
        raise typer.Exit(1)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(draft)
        emit({"problem_id": problem_id, "output": output}, as_json=json_out)
        return

    typer.echo(draft)
