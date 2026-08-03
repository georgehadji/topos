# ruff: noqa: RUF001
"""Unit tests: newsletter digest rendering.

Pure formatting helpers get literal inputs; ``build_newsletter`` gets a mocked
asyncpg pool, same shape as tests/unit/test_er.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from topos.service.newsletter import build_newsletter

_DAY = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "problem_id": "p1",
        "title": "Water Supply Disruption",
        "category": "water_supply_disruption",
        "status": "candidate",
        "geo_conf": 0.85,
        "lat": 40.665,
        "lon": 22.928,
        "first_seen": _DAY,
        "authority": "ΕΥΑΘ",
        "claim_value": '{"description": "pipe burst", "location": "Σταυρούπολη"}',
        "confidence": 0.9,
        "uri": "https://example.gr/a",
        "source_kind": "sonar_web",
    }
    base.update(overrides)
    return base


def _mock_pool(rows: list[dict[str, Any]]) -> MagicMock:
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    return pool


@pytest.mark.asyncio
async def test_empty_corpus_says_so_rather_than_rendering_an_empty_shell() -> None:
    out = await build_newsletter(_mock_pool([]))
    assert "No findings in this period." in out


@pytest.mark.asyncio
async def test_renders_claim_summary_details_and_source() -> None:
    out = await build_newsletter(_mock_pool([_row()]))

    assert "## 2026-08-03" in out
    assert "### Water Supply Disruption" in out
    assert "pipe burst" in out
    assert "- Location: Σταυρούπολη" in out
    assert "**Authority:** ΕΥΑΘ" in out
    assert "40.6650, 22.9280" in out
    assert "https://example.gr/a" in out
    assert "*(confidence 0.90)*" in out


@pytest.mark.asyncio
async def test_merged_problems_are_counted_but_never_listed() -> None:
    """A merged row is a duplicate ER folded away — printing it double-reports
    the same real-world incident."""
    rows = [_row(), _row(problem_id="p2", status="merged", claim_value=None)]

    out = await build_newsletter(_mock_pool(rows))

    assert "1 duplicate report(s) merged" in out
    assert out.count("### Water Supply Disruption") == 1


@pytest.mark.asyncio
async def test_two_problems_same_category_are_numbered_not_collapsed() -> None:
    rows = [_row(), _row(problem_id="p2", lat=40.7, lon=22.8)]

    out = await build_newsletter(_mock_pool(rows))

    assert "#### Report 1 of 2" in out
    assert "#### Report 2 of 2" in out
    assert out.count("### Water Supply Disruption") == 1


@pytest.mark.asyncio
async def test_single_problem_gets_no_redundant_report_heading() -> None:
    out = await build_newsletter(_mock_pool([_row()]))
    assert "Report 1 of 1" not in out


@pytest.mark.asyncio
async def test_distinct_title_is_shown_instead_of_a_report_number() -> None:
    out = await build_newsletter(_mock_pool([_row(title="Burst main on Egnatia")]))
    assert "#### Burst main on Egnatia" in out


@pytest.mark.asyncio
async def test_unresolved_location_is_stated_not_omitted() -> None:
    """Silence would read as 'no location field'; Topos reports the gap."""
    out = await build_newsletter(_mock_pool([_row(lat=None, lon=None, geo_conf=None)]))
    assert "**Location:** not resolved" in out


@pytest.mark.asyncio
async def test_ordinal_keys_keep_lowercase_suffixes() -> None:
    """str.title() would render contract_budget_5th as 'Contract Budget 5Th'."""
    rows = [_row(claim_value='{"description": "d", "contract_budget_5th": 330000.0}')]

    out = await build_newsletter(_mock_pool(rows))

    assert "Contract Budget 5th: 330,000" in out
    assert "5Th" not in out


@pytest.mark.asyncio
async def test_non_integer_budget_keeps_thousands_separator() -> None:
    rows = [_row(claim_value='{"description": "d", "original_budget": 2390560.77}')]
    out = await build_newsletter(_mock_pool(rows))
    assert "Original Budget: 2,390,560.77" in out


@pytest.mark.asyncio
async def test_list_and_bool_details_render_readably() -> None:
    rows = [
        _row(
            claim_value=(
                '{"description": "d", "affected_streets": ["Α", "Β"], "extension_approved": true}'
            )
        )
    ]

    out = await build_newsletter(_mock_pool(rows))

    assert "Affected Streets: Α, Β" in out
    assert "Extension Approved: yes" in out


@pytest.mark.asyncio
async def test_unparseable_claim_value_still_renders_as_text() -> None:
    """Never drop a finding because its JSON was malformed."""
    out = await build_newsletter(_mock_pool([_row(claim_value="not json at all")]))
    assert "not json at all" in out


@pytest.mark.asyncio
async def test_since_and_until_are_passed_through_to_the_query() -> None:
    pool = _mock_pool([])
    since, until = datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 8, 4, tzinfo=UTC)

    await build_newsletter(pool, since=since, until=until)

    args = pool.acquire.return_value.__aenter__.return_value.fetch.call_args[0]
    assert args[1] == since
    assert args[2] == until


@pytest.mark.asyncio
async def test_multiple_days_each_get_their_own_section() -> None:
    rows = [_row(), _row(problem_id="p2", first_seen=datetime(2026, 8, 2, tzinfo=UTC))]

    out = await build_newsletter(_mock_pool(rows))

    assert "## 2026-08-02" in out
    assert "## 2026-08-03" in out
    assert "2026-08-02 – 2026-08-03" in out
