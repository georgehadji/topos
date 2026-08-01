"""The headless CLI contract that external agents depend on (AGENTS.md).

Only the commands that need neither a database nor the network are covered here;
the DB-backed ones are exercised by tests/contract. What is locked down:

  - discovery works with no configuration at all
  - `--json` puts exactly one JSON object on stdout
  - failures exit 1 and name the valid options instead of a bare traceback
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from topos.interfaces.cli.main import cli

runner = CliRunner()


def _json_stdout(args: list[str]) -> Any:
    """Run *args*, require exit 0, and parse stdout as a single JSON object."""
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, f"{args} exited {result.exit_code}: {result.output}"
    return json.loads(result.stdout)


def test_help_exits_zero_without_any_configuration() -> None:
    assert runner.invoke(cli, ["--help"]).exit_code == 0


def test_version_json_is_one_object() -> None:
    assert "version" in _json_stdout(["version", "--json"])


def test_sources_json_lists_every_plugin_with_its_config_fields() -> None:
    """`sources --json` is how an agent discovers what `--set` accepts."""
    sources = _json_stdout(["sources", "--json"])

    assert "diavgeia" in sources
    # Each value is the plugin's config model, so every key is a valid --set target.
    assert sources["diavgeia"]["page_size"] == 50
    assert all(isinstance(config, dict) and config for config in sources.values())


@pytest.mark.parametrize(
    ("args", "expected_in_error"),
    [
        (["backfill", "--source", "nope", "--json"], "unknown source"),
        (["backfill", "--source", "diavgeia", "--set", "nope=1", "--json"], "no field"),
        (["backfill", "--source", "diavgeia", "--set", "novalue", "--json"], "key=value"),
        (["cost", "--month", "2026-99", "--json"], "YYYY-MM"),
    ],
)
def test_bad_input_exits_one_and_explains(args: list[str], expected_in_error: str) -> None:
    """Failures must be actionable: exit 1, and say what would have been valid."""
    result = runner.invoke(cli, args)

    assert result.exit_code == 1
    assert expected_in_error in result.output


def test_worker_offers_a_bounded_run() -> None:
    """Without --drain the worker never returns, which is unusable non-interactively."""
    result = runner.invoke(cli, ["worker", "--help"])

    assert result.exit_code == 0
    assert "--drain" in result.output


def test_unknown_source_names_the_valid_ones() -> None:
    """An agent that guesses wrong gets the real list back, not just a rejection."""
    result = runner.invoke(cli, ["backfill", "--source", "nope", "--json"])

    assert "diavgeia" in result.output
    assert "news" in result.output
