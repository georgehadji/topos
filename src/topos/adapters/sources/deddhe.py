"""ΔΕΔΔΗΕ (HEDNO) scheduled power outages.

Reads the operator's public outage application at
``siteapps.deddie.gr/Outages2Public/``. It is an ASP.NET MVC form, not an
API: POST ``PrefectureID`` and it re-renders the page with a results table.
ΘΕΣΣΑΛΟΝΙΚΗΣ is prefecture 23. No auth, no token — the unobtrusive-ajax form
posts anonymously.

**This module previously fabricated its output.** The old implementation
called ``deddie.gr/api/v1/outages`` — which returns 404, and has for some
time — and on failure fell through to two hardcoded "sample" outages
described in the source as "beautiful Greek power outage sample fallbacks
(100% consistent with real ΔΕΔΔΗΕ notices)". Because the API is dead, that
fallback was not a fallback: it was the only code path. Every backfill
injected two invented outages naming real streets in Χαριλάου and the centre,
which then flowed through extraction into ``problem`` rows indistinguishable
from real findings.

Nothing here invents data now. If the fetch or the parse fails, the plugin
logs and yields nothing — ADR-012, and the whole premise of a product whose
value is that every claim traces to a real document.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import AsyncIterator

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register

logger = logging.getLogger(__name__)

_UA = {
    "User-Agent": "Topos/0.1",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded",
}

# Column order of the results table, verified 2026-08-04.
_FROM, _TO, _MUNICIPALITY, _AREA, _NOTE_NO, _PURPOSE = range(6)
_EXPECTED_COLUMNS = 6


class DeddheConfig(BaseModel):
    """``prefecture_id`` 23 is ΘΕΣΣΑΛΟΝΙΚΗΣ in ΔΕΔΔΗΕ's own numbering, which
    is neither ELSTAT's nor alphabetical — read it off the page's
    ``PrefectureID`` select if it ever needs changing."""

    base_url: str = "https://siteapps.deddie.gr/outages2public/"
    prefecture_id: int = 23
    max_items: int = 20


@register
class DeddhePlugin(SourcePlugin):
    """Plugin for ΔΕΔΔΗΕ — scheduled electricity outages."""

    kind = "deddhe"
    config_model = DeddheConfig

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = DeddheConfig.model_validate(config)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=_UA) as client:
            try:
                resp = await client.post(
                    cfg.base_url,
                    content=f"PrefectureID={cfg.prefecture_id}&MunicipalityID=",
                )
                resp.raise_for_status()
                html = resp.text
            except httpx.HTTPError as exc:
                # No fallback. A missing source is missing, not simulated.
                logger.warning("deddhe.fetch_failed err=%s", exc)
                return

        rows = _parse_outages(html)
        if not rows:
            # Genuinely-zero outages and a layout change look identical from
            # here, so say so rather than implying a clean empty result.
            logger.info("deddhe.no_outages prefecture=%s", cfg.prefecture_id)

        for row in rows[: cfg.max_items]:
            text = _render(row)
            # The note number column is empty in practice, so identity comes
            # from the content: the same outage re-listed tomorrow keys the
            # same, and artifact's (source, uri, sha256) conflict absorbs it.
            key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            yield PluginArtifact(
                uri=f"deddhe://{key}",
                data=text.encode("utf-8"),
                mime="text/plain",
                meta={
                    "municipality": row[_MUNICIPALITY],
                    "from": row[_FROM],
                    "to": row[_TO],
                    "purpose": row[_PURPOSE],
                },
            )


def _parse_outages(html: str) -> list[list[str]]:
    """Data rows of the results table, header and empty rows dropped."""
    table = re.search(r"(?is)<table.*?</table>", html)
    if table is None:
        return []

    rows: list[list[str]] = []
    for raw in re.findall(r"(?is)<tr.*?</tr>", table.group(0)):
        cells = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip()
            for cell in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", raw)
        ]
        if len(cells) != _EXPECTED_COLUMNS:
            continue
        # The header repeats the literal column captions; skip that row only.
        if cells[_FROM].startswith("Από"):
            continue
        if not any(cells):
            continue
        rows.append(cells)
    return rows


def _render(row: list[str]) -> str:
    """One outage as a short Greek document. Empty columns are left out."""
    parts = [f"Προγραμματισμένη διακοπή ρεύματος: {row[_MUNICIPALITY]}."]
    if row[_FROM] and row[_TO]:
        parts.append(f"Από {row[_FROM]} έως {row[_TO]}.")
    if row[_PURPOSE]:
        parts.append(f"Σκοπός διακοπής: {row[_PURPOSE]}.")
    if row[_AREA]:
        parts.append(f"Περιοχή: {row[_AREA]}")
    if row[_NOTE_NO]:
        parts.append(f"Αριθμός σημειώματος: {row[_NOTE_NO]}.")
    return " ".join(parts)
