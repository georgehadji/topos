"""ΚΗΜΔΗΣ source plugin.

Fetches public contracts from the Greek Central Electronic Registry
for Public Procurement (https://www.eprocurement.gov.gr/).

No auth key required for basic search.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register


class KhmidhsConfig(BaseModel):
    """Config stored in source.config jsonb."""

    base_url: str = "https://www.eprocurement.gov.gr"
    page_size: int = 20
    org: str = ""
    max_pages: int = 0


@register
class KhmidhsPlugin(SourcePlugin):
    """Plugin for eprocurement.gov.gr — public contract announcements."""

    kind = "khmdhs"
    config_model = KhmidhsConfig

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = KhmidhsConfig.model_validate(config)
        page = 0

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            while True:
                params: dict[str, str] = {
                    "size": str(cfg.page_size),
                    "page": str(page),
                    "sort": "publicationDate",
                    "order": "desc",
                }
                if cfg.org:
                    params["org"] = cfg.org

                try:
                    resp = await client.get(
                        f"{cfg.base_url}/api/contracts/search",
                        params=params,
                        headers={"Accept": "application/json"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except httpx.HTTPStatusError:
                    break

                if isinstance(data, list):
                    contracts = data
                elif isinstance(data, dict):
                    contracts = (
                        data.get("data")
                        or data.get("results")
                        or ([data] if data.get("id") else [])
                    )
                else:
                    contracts = []
                if not contracts:
                    break

                for item in contracts if isinstance(contracts, list) else []:
                    if not isinstance(item, dict):
                        continue
                    cid = item.get("id", "") or item.get("contractId", "")
                    if not cid:
                        continue

                    pdf_url = (
                        item.get("documentUrl", "") or item.get("pdfUrl", "") or item.get("url", "")
                    )
                    if not pdf_url:
                        continue

                    try:
                        pdf_resp = await client.get(pdf_url)
                        pdf_resp.raise_for_status()
                    except httpx.HTTPStatusError:
                        continue

                    yield PluginArtifact(
                        uri=f"khmdhs://{cid}",
                        data=pdf_resp.content,
                        mime=pdf_resp.headers.get("content-type", "application/pdf"),
                        meta={
                            "contract_id": cid,
                            "subject": item.get("subject", ""),
                            "contractingAuthority": item.get("contractingAuthority", ""),
                            "budget": item.get("budget"),
                            "publicationDate": _parse_date(item.get("publicationDate")),
                        },
                    )

                page += 1
                if cfg.max_pages > 0 and page >= cfg.max_pages:
                    break


def _parse_date(ts: int | str | None) -> str | None:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat()
        return str(ts)
    except (ValueError, OSError):
        return None
