"""Output helpers shared by every ``topos-cli`` command.

Commands print either human-readable ``key: value`` lines or a single JSON
object (``--json``). Agents and CI should use ``--json``: it is one line, on
stdout, and always parseable. Errors go to stderr and exit 1.
"""

from __future__ import annotations

import json
from typing import Any, NoReturn

import typer


def emit(payload: dict[str, Any], *, as_json: bool) -> None:
    """Write *payload* to stdout as JSON or as aligned key/value lines."""
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, default=str))
        return
    width = max((len(k) for k in payload), default=0)
    for key, value in payload.items():
        typer.echo(f"{key.ljust(width)}  {value}")


def fail(message: str, *, json_out: bool) -> NoReturn:
    """Report an error on stderr and exit 1."""
    if json_out:
        typer.echo(json.dumps({"ok": False, "error": message}, ensure_ascii=False), err=True)
    else:
        typer.echo(f"error: {message}", err=True)
    raise typer.Exit(1)
