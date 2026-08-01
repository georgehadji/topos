"""``topos-cli`` — the headless entrypoint for Topos.

Every command is non-interactive, needs no TTY, and can emit a single JSON
object with ``--json``, so an agent or CI job can drive the whole system::

    uv run topos-cli --help
    uv run topos-cli sources --json
    uv run topos-cli health --json
    uv run topos-cli seed
    uv run topos-cli backfill --source diavgeia --limit 100 --dry-run --json
    uv run topos-cli cost --month current --json
    uv run topos-cli export problems --output problems.jsonl
    uv run topos-cli worker
    uv run topos-cli serve --port 8000

Exit status is 0 on success and 1 on failure, so `&&` chaining is safe.

This module lives in interfaces/: it is the only place allowed to resolve a
source ``kind`` to a concrete plugin and hand it to service/ (see the
.importlinter contract ``service-ports-only``).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import sys
from typing import Any

import asyncpg
import typer
import uvicorn

from topos import __version__
from topos.adapters.blob.s3 import S3BlobStore
from topos.adapters.llm.sonar import SonarProvider
from topos.adapters.llm.xai import XaiProvider
from topos.adapters.sources import registry
from topos.adapters.sources.websearch import available_engines
from topos.config import get_settings, is_placeholder_key
from topos.interfaces.cli.admin_cmd import cost, seed
from topos.interfaces.cli.export_cmd import cli as export_cli
from topos.interfaces.cli.io import emit, fail
from topos.interfaces.cli.worker import main as worker_main
from topos.service.backfill import backfill_source

cli = typer.Typer(
    name="topos-cli",
    help="Topos — constituency problem intelligence for Α΄ Θεσσαλονίκης.",  # noqa: RUF001
    no_args_is_help=True,
    add_completion=False,
)
cli.add_typer(export_cli, name="export")
cli.command("seed")(seed)
cli.command("cost")(cost)

# Fields a plugin config may use for "how much to pull", most specific first.
_LIMIT_FIELDS = ("max_per_fetch", "max_items", "max_posts", "max_per_feed", "max_pages")


@cli.command()
def version(json_out: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """Print the installed Topos version."""
    emit({"version": __version__}, as_json=json_out)


@cli.command()
def sources(json_out: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """List every registered source plugin and its config fields.

    Needs no database and no network — use it to discover what ``backfill
    --source`` accepts.
    """
    out: dict[str, Any] = {}
    for kind in sorted(registry.list_kinds()):
        plugin_cls = registry.get(kind)
        if plugin_cls is None:  # pragma: no cover - list_kinds is the key set
            continue
        out[kind] = plugin_cls.config_model().model_dump(mode="json")
    if json_out:
        emit(out, as_json=True)
        return
    for kind, config in out.items():
        typer.echo(f"{kind}")
        for key, value in config.items():
            typer.echo(f"  {key} = {json.dumps(value, ensure_ascii=False)}")


@cli.command()
def health(
    db_dsn: str = typer.Option("", help="Override TOPOS_DB_DSN."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Report configuration and database reachability. Exit 1 if the DB is down."""
    settings = get_settings()
    report = asyncio.run(_probe(db_dsn or settings.db_dsn))
    report["llm_provider"] = settings.llm_provider
    report["llm_key_present"] = bool(settings.llm_api_key or settings.xai_api_key)
    # "mock" means claims are fabricated, not extracted. Surface it loudly.
    report["llm_mode"] = "mock" if is_placeholder_key(settings.llm_api_key) else "live"
    report["s3_endpoint"] = settings.s3_endpoint
    report["sources_registered"] = len(registry.list_kinds())
    # Which discovery paths can actually reach the outside world right now.
    live = not is_placeholder_key(settings.llm_api_key)
    report["search"] = {
        "web_engines": available_engines(settings),  # brave, google_cse, bing, ...
        "sonar": "perplexity_direct"
        if not is_placeholder_key(settings.perplexity_api_key)
        else ("openrouter" if live else False),
        "xai_web_and_x_search": not is_placeholder_key(settings.xai_api_key),
    }

    emit(report, as_json=json_out)
    if not report["db_ok"]:
        raise typer.Exit(1)


async def _probe(dsn: str) -> dict[str, Any]:
    """Connect and read the few facts that tell you whether the stack is usable."""
    report: dict[str, Any] = {"db_ok": False, "dsn_configured": bool(dsn)}
    try:
        conn = await asyncpg.connect(dsn, timeout=5)
    except Exception as exc:
        report["db_error"] = f"{type(exc).__name__}: {exc}"
        return report

    report["db_ok"] = True
    try:
        # Each probe is optional: a reachable but un-migrated database should
        # still report db_ok=True, with the missing pieces simply absent.
        with contextlib.suppress(Exception):
            report["migration"] = await conn.fetchval("SELECT version_num FROM alembic_version")
        with contextlib.suppress(Exception):
            report["sources_seeded"] = await conn.fetchval("SELECT count(*) FROM source")
        with contextlib.suppress(Exception):
            report["pipeline_pending"] = await conn.fetchval(
                "SELECT count(*) FROM pipeline WHERE state <> 'done'::pipe_state"
            )
        with contextlib.suppress(Exception):
            report["problems"] = await conn.fetchval("SELECT count(*) FROM problem")
    finally:
        await conn.close()
    return report


@cli.command()
def backfill(
    source: str = typer.Option(..., help="Registered source kind, e.g. 'diavgeia'."),
    limit: int = typer.Option(0, help="Cap artifacts fetched. 0 = plugin default."),
    org: str = typer.Option("", help="Organisation filter, for sources that support one."),
    set_: list[str] | None = typer.Option(  # noqa: B008 — Typer's declaration style
        None, "--set", help="Override any config field: --set page_size=25 (repeatable)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and count, write nothing."),
    db_dsn: str = typer.Option("", help="Override TOPOS_DB_DSN."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Ingest documents from a source and enqueue them for the worker.

    Resolves *source* through the plugin registry here in interfaces/, then
    hands the constructed plugin to the service layer.
    """
    plugin_cls = registry.get(source)
    if plugin_cls is None:
        known = ", ".join(sorted(registry.list_kinds()))
        fail(f"unknown source {source!r}. Known sources: {known}", json_out=json_out)

    try:
        config = _build_config(plugin_cls.config_model, limit=limit, org=org, overrides=set_ or [])
    except ValueError as exc:
        fail(str(exc), json_out=json_out)

    settings = get_settings()
    dsn = db_dsn or settings.db_dsn
    plugin = _build_plugin(source, plugin_cls, settings)
    blob = _build_blob(settings)
    try:
        result = asyncio.run(_run_backfill(dsn, source, plugin, config, blob=blob, dry_run=dry_run))
    except Exception as exc:
        fail(f"backfill failed: {type(exc).__name__}: {exc}", json_out=json_out)

    emit(result, as_json=json_out)


def _build_plugin(kind: str, plugin_cls: Any, settings: Any) -> Any:
    """Construct a source plugin, injecting whatever provider it needs.

    The search-backed sources do not fetch anything without a provider — they
    log and yield nothing. interfaces/ is the only layer allowed to pick a
    concrete adapter, so the wiring lives here rather than in the plugin.
    """
    if kind == "social":
        # X Search runs through the xAI Responses API, which is the only
        # endpoint exposing the x_search tool.
        return plugin_cls(
            XaiProvider(
                api_key=settings.xai_api_key,
                base_url=settings.xai_base_url,
                fallback_api_key=settings.llm_api_key,
                fallback_base_url=settings.llm_base_url,
                fallback_model=settings.llm_fallback_model or "x-ai/grok-4.5",
            )
        )
    if kind == "sonar_web":
        # Sonar searches the web before every completion. Perplexity direct
        # first, OpenRouter second.
        return plugin_cls(
            SonarProvider(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                perplexity_api_key=settings.perplexity_api_key,
                perplexity_base_url=settings.perplexity_base_url,
                perplexity_model=settings.perplexity_model,
            )
        )
    if kind == "websearch":
        return plugin_cls(settings)
    return plugin_cls()


def _build_config(model: Any, *, limit: int, org: str, overrides: list[str]) -> Any:
    """Build a plugin config from its defaults plus CLI overrides."""
    fields: dict[str, Any] = {}
    known = set(model.model_fields)

    if limit > 0:
        for name in _LIMIT_FIELDS:
            if name in known:
                fields[name] = limit
                break
    if org and "org" in known:
        fields["org"] = org

    for item in overrides:
        key, sep, raw = item.partition("=")
        if not sep:
            raise ValueError(f"--set expects key=value, got {item!r}")
        key = key.strip()
        if key not in known:
            raise ValueError(f"{model.__name__} has no field {key!r}. Try `topos-cli sources`.")
        # Let JSON carry ints/bools/lists; anything else is a plain string.
        try:
            fields[key] = json.loads(raw)
        except json.JSONDecodeError:
            fields[key] = raw

    try:
        return model(**fields)
    except Exception as exc:
        raise ValueError(f"invalid config: {exc}") from exc


def _build_blob(settings: Any) -> S3BlobStore:
    """The object store that holds fetched artifact bytes."""
    return S3BlobStore(
        endpoint_url=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        access_key_id=settings.s3_access_key,
        secret_access_key=settings.s3_secret_key,
    )


async def _run_backfill(
    dsn: str, source: str, plugin: Any, config: Any, *, blob: Any, dry_run: bool
) -> dict[str, Any]:
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    if pool is None:  # pragma: no cover - asyncpg returns None only on bad config
        raise RuntimeError("could not create a connection pool")
    try:
        return await backfill_source(pool, source, plugin, config, blob=blob, dry_run=dry_run)
    finally:
        await pool.close()


@cli.command()
def worker(
    drain: bool = typer.Option(
        False, "--drain", help="Exit once the queue is empty instead of idling forever."
    ),
) -> None:
    """Run the pipeline worker loop (SKIP LOCKED claims).

    Runs until SIGINT/SIGTERM. Use --drain for a bounded run that processes
    everything pending and then exits 0 — the mode batch jobs and agents want.
    """
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(worker_main(drain=drain))


@cli.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind address."),  # noqa: S104
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on source changes."),
) -> None:
    """Run the FastAPI HTTP API with uvicorn."""
    uvicorn.run(
        "topos.interfaces.http.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=get_settings().log_level.lower(),
    )


@cli.command()
def pipeline(
    db_dsn: str = typer.Option("", help="Override TOPOS_DB_DSN."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show how many artifacts sit in each pipeline state."""
    dsn = db_dsn or get_settings().db_dsn
    try:
        counts = asyncio.run(_pipeline_counts(dsn))
    except Exception as exc:
        fail(f"pipeline query failed: {type(exc).__name__}: {exc}", json_out=json_out)
    emit(counts, as_json=json_out)


async def _pipeline_counts(dsn: str) -> dict[str, Any]:
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        rows = await conn.fetch(
            "SELECT state::text AS state, count(*) AS n FROM pipeline GROUP BY 1 ORDER BY 1"
        )
        return {row["state"]: row["n"] for row in rows}
    finally:
        await conn.close()


def main() -> None:
    """Console-script entry point (``topos-cli``).

    Greek is data here, not decoration: on Windows the default console encoding
    is a legacy codepage that silently mangles it, so a caller redirecting
    ``--json`` to a file gets bytes that are not valid UTF-8. Pin both streams
    to UTF-8 before Typer runs.
    """
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    cli()


if __name__ == "__main__":
    main()
