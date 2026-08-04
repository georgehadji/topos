# ruff: noqa: RUF001
"""Unit tests: ΔΕΔΔΗΕ outage table parsing.

The fixture is a trimmed copy of the real response captured 2026-08-04.

The most important test here is the negative one: this module used to emit
hardcoded "sample" outages whenever the upstream call failed, and since the
upstream endpoint had 404'd, that fallback was the only path that ever ran.
A failed fetch must now produce nothing at all.
"""

from __future__ import annotations

import httpx
import pytest

from topos.adapters.sources.deddhe import (
    DeddheConfig,
    DeddhePlugin,
    _parse_outages,
    _render,
)

_TABLE = """
<table class="table">
<tr><th>Από ημ/νία και ώρα</th><th>Έως ημ/νία και ώρα</th><th>Δήμος/κοινότητα</th>
<th>Περιγραφή περιοχής</th><th>Αριθμός Σημειώματος</th><th>Σκοπός διακοπής</th></tr>
<tr><td>6/8/2026 8:00:00 πμ</td><td>6/8/2026 11:00:00 πμ</td>
<td>ΘΕΡΜΗΣ Δ.Ε.ΒΑΣΙΛΙΚΩΝ</td><td>Επαρχιακή οδός ΛΙΒΑΔΙΟΥ - ΒΑΣΙΛΙΚΩΝ</td>
<td></td><td>Κατασκευές</td></tr>
<tr><td>7/8/2026 8:00:00 πμ</td><td>7/8/2026 2:30:00 μμ</td>
<td>ΔΕΛΤΑ</td><td>τμήμα της ΜΑΚΕΔΟΝΟΜΑΧΩΝ</td><td></td><td>Κατασκευές</td></tr>
</table>
"""


def test_parses_data_rows_and_drops_the_header() -> None:
    rows = _parse_outages(_TABLE)
    assert len(rows) == 2
    assert rows[0][2] == "ΘΕΡΜΗΣ Δ.Ε.ΒΑΣΙΛΙΚΩΝ"
    assert rows[1][2] == "ΔΕΛΤΑ"


def test_no_table_yields_no_rows() -> None:
    """A layout change must produce nothing, never a guess."""
    assert _parse_outages("<html><body>no table here</body></html>") == []


def test_rows_with_unexpected_column_counts_are_skipped() -> None:
    html = "<table><tr><td>a</td><td>b</td></tr></table>"
    assert _parse_outages(html) == []


def test_render_includes_municipality_window_purpose_and_area() -> None:
    row = ["6/8/2026 8:00", "6/8/2026 11:00", "ΔΕΛΤΑ", "οδός Χ", "", "Κατασκευές"]
    text = _render(row)
    assert "ΔΕΛΤΑ" in text
    assert "Από 6/8/2026 8:00 έως 6/8/2026 11:00" in text
    assert "Κατασκευές" in text
    assert "οδός Χ" in text


def test_render_omits_the_empty_note_number() -> None:
    """The note-number column is empty in practice; it must not print a
    dangling 'Αριθμός σημειώματος:' label."""
    row = ["a", "b", "ΔΕΛΤΑ", "περιοχή", "", "Κατασκευές"]
    assert "σημειώματος" not in _render(row)


@pytest.mark.asyncio
async def test_failed_fetch_yields_nothing_and_never_fabricates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the fabrication bug: the old code answered an upstream
    failure with two invented outages naming real Thessaloniki streets."""

    async def boom(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("upstream down")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    produced = [a async for a in DeddhePlugin().fetch(DeddheConfig())]

    assert produced == []


def _response(text: str) -> httpx.Response:
    """A 200 with its request set — raise_for_status() needs one."""
    return httpx.Response(
        200, text=text, request=httpx.Request("POST", "https://siteapps.deddie.gr/outages2public/")
    )


@pytest.mark.asyncio
async def test_empty_result_table_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def empty(*args: object, **kwargs: object) -> httpx.Response:
        return _response("<table><tr><th>Από ημ/νία και ώρα</th></tr></table>")

    monkeypatch.setattr(httpx.AsyncClient, "post", empty)

    produced = [a async for a in DeddhePlugin().fetch(DeddheConfig())]

    assert produced == []


@pytest.mark.asyncio
async def test_real_rows_become_artifacts_with_content_derived_uris(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def table(*args: object, **kwargs: object) -> httpx.Response:
        return _response(_TABLE)

    monkeypatch.setattr(httpx.AsyncClient, "post", table)

    produced = [a async for a in DeddhePlugin().fetch(DeddheConfig())]

    assert len(produced) == 2
    assert all(a.uri.startswith("deddhe://") for a in produced)
    # Distinct outages must not collide onto one artifact id.
    assert produced[0].uri != produced[1].uri
    assert produced[0].meta is not None
    assert produced[0].meta["municipality"] == "ΘΕΡΜΗΣ Δ.Ε.ΒΑΣΙΛΙΚΩΝ"
