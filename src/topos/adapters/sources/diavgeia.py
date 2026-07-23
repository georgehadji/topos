"""Διαύγεια source plugin.

Fetches decisions from the Greek Government Transparency Portal
(diavgeia.gov.gr). Implements SourcePlugin.

Διαύγεια API: https://diavgeia.gov.gr/opendata/search
No auth key needed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register


class DiavgeiaConfig(BaseModel):
    """Config stored in source.config jsonb."""

    base_url: str = "https://diavgeia.gov.gr/opendata"
    max_per_fetch: int = 5
    org: str = ""


@register
class DiavgeiaPlugin(SourcePlugin):
    """Plugin for diavgeia.gov.gr — Greek government decisions."""

    kind = "diavgeia"
    config_model = DiavgeiaConfig

    async def fetch(
        self, config: BaseModel
    ) -> AsyncIterator[PluginArtifact]:
        cfg = DiavgeiaConfig.model_validate(config)
        params: dict[str, str] = {
            "size": str(cfg.max_per_fetch),
            "sort": "ada",
            "order": "desc",
        }
        if cfg.org:
            params["org"] = cfg.org

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{cfg.base_url}/search",
                params=params,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        decisions = _extract_decisions(data)
        for item in decisions:
            ada = item.get("ada", "")
            if not ada:
                continue

            doc_url = item.get("documentUrl", "") or item.get("url", "")
            # Διαύγεια v2: document download via luminapi
            pdf_url = f"https://diavgeia.gov.gr/luminapi/api/decisions/{ada}/document"

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client2:
                pdf_resp = await client2.get(pdf_url)
                pdf_resp.raise_for_status()
                yield PluginArtifact(
                    uri=f"diavgeia://{ada}",
                    data=pdf_resp.content,
                    mime=pdf_resp.headers.get("content-type", "application/pdf"),
                    meta={
                        "ada": ada,
                        "subject": item.get("subject", ""),
                        "organization": item.get("organization", ""),
                        "decisionType": item.get("decisionType", ""),
                        "url": doc_url,
                    },
                )


def _extract_decisions(data: Any) -> list[dict[str, Any]]:
    """Extract decisions from various API response shapes."""
    if isinstance(data, dict):
        for key in ("data", "decisions", "results", "content"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        for key in ("_embedded",):
            val = data.get(key)
            if isinstance(val, dict):
                return _extract_decisions(val)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []
