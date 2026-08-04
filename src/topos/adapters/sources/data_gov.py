"""data.gov.gr — the national open-data portal, CKAN 2.11.3.

The API moved: there is no ``/api/v1/*`` and no token flow any more. It is
plain anonymous CKAN at ``/api/3/action/``, 22,440 datasets, of which 364 are
Thessaloniki-scoped across two publisher organisations (the current
``dimos-thessalonikis-2026`` and the legacy ``dimosthessalonikis``).

**Greek free-text search is useless here and must not be used.** ``q=Θεσσαλονίκη``
matches 15,963 of 22,440 datasets — essentially everything — while
``fq=title:Θεσσαλονίκη`` matches zero. The index does not tokenise Greek. Filter
by ``fq=organization:`` instead, which is exact.

What this yields is *dataset metadata* — titles and notes describing what a
published dataset contains. A dataset is not itself an incident, so most
records extract to nothing. It earns its place because the descriptions do
surface standing problems (recorded pavement defects, complaint registers)
and because it is the discovery path to the resources behind them.

Two other CKAN actions to know about: ``organization_list`` rejects GET with
400 "Please use POST", and ``datastore_search_sql`` is disabled entirely.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Topos/0.1"}
_MIN_TEXT = 80


class DataGovConfig(BaseModel):
    base_url: str = "https://data.gov.gr/api/3/action/package_search"
    # Both the current and legacy publisher orgs for the municipality.
    organizations: list[str] = ["dimos-thessalonikis-2026", "dimosthessalonikis"]
    rows: int = 50


@register
class DataGovPlugin(SourcePlugin):
    """Thessaloniki-scoped dataset metadata from data.gov.gr."""

    kind = "data_gov"
    config_model = DataGovConfig

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = DataGovConfig.model_validate(config)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=_UA) as client:
            for org in cfg.organizations:
                try:
                    resp = await client.get(
                        cfg.base_url,
                        params={"fq": f"organization:{org}", "rows": cfg.rows},
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("data_gov.fetch_failed org=%s err=%s", org, exc)
                    continue

                for dataset in _datasets(payload):
                    text = _render(dataset)
                    if len(text) < _MIN_TEXT:
                        continue
                    yield PluginArtifact(
                        uri=f"data_gov://{dataset.get('name') or dataset.get('id')}",
                        data=text.encode("utf-8"),
                        mime="text/plain",
                        meta={"organization": org, "dataset_id": dataset.get("id")},
                    )


def _datasets(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    results = result.get("results")
    return [d for d in results if isinstance(d, dict)] if isinstance(results, list) else []


def _render(dataset: dict[str, Any]) -> str:
    """Dataset title and notes as a short document. Absent fields are skipped."""
    lines = []
    if title := dataset.get("title"):
        lines.append(f"Σύνολο δεδομένων: {title}")
    if notes := dataset.get("notes"):
        lines.append(str(notes).strip())
    resources = dataset.get("resources")
    if isinstance(resources, list) and resources:
        formats = sorted(
            {str(r.get("format")) for r in resources if isinstance(r, dict) and r.get("format")}
        )
        if formats:
            lines.append(f"Μορφές: {', '.join(formats)}")
    return "\n".join(lines).strip()
