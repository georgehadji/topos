"""Διαύγεια source plugin — paginated + incremental.

Fetches decisions from the Greek Government Transparency Portal
(diavgeia.gov.gr). Paginates through all pages and supports
incremental fetch by tracking ``last_ada`` in source config.

Διαύγεια v2 API: https://diavgeia.gov.gr/opendata/search
Document download: /luminapi/api/decisions/{ada}/document
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register


class DiavgeiaConfig(BaseModel):
    """Config stored in source.config jsonb.

    ``last_ada`` tracks the last fetched ADA so subsequent runs
    only fetch newer decisions. Set to ``""`` to force a full backfill.
    """

    base_url: str = "https://diavgeia.gov.gr/opendata"
    page_size: int = 50
    org: str = ""
    last_ada: str = ""
    max_pages: int = 0  # 0 = unlimited


_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Topos/0.1 (constituency intelligence; contact@topos.local)",
}


@register
class DiavgeiaPlugin(SourcePlugin):
    """Plugin for diavgeia.gov.gr — Greek government decisions.

    Paginates through ``/opendata/search``, yields PDF artifacts.
    Incremental: set ``source.config->>'last_ada'`` to the last ADA
    fetched; the plugin uses ``fromAda`` param to skip older items.
    """

    kind = "diavgeia"
    config_model = DiavgeiaConfig

    async def fetch(
        self, config: BaseModel
    ) -> AsyncIterator[PluginArtifact]:
        cfg = DiavgeiaConfig.model_validate(config)
        seen = 0
        page = 0

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            while True:
                # Build paginated request
                params: dict[str, str] = {
                    "size": str(cfg.page_size),
                    "sort": "ada",
                    "order": "desc",
                }
                if cfg.org:
                    params["org"] = cfg.org
                if cfg.last_ada:
                    params["fromAda"] = cfg.last_ada

                resp = await client.get(
                    f"{cfg.base_url}/search",
                    params=params,
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                decisions = _extract_decisions(data)

                if not decisions:
                    break  # no more results

                for item in decisions:
                    ada = item.get("ada", "")
                    if not ada:
                        continue

                    # Stop if we hit the last_ada boundary
                    if cfg.last_ada and ada <= cfg.last_ada:
                        return

                    # Download the actual PDF
                    pdf_url = (
                        f"https://diavgeia.gov.gr/luminapi"
                        f"/api/decisions/{ada}/document"
                    )
                    try:
                        pdf_resp = await client.get(pdf_url)
                        pdf_resp.raise_for_status()
                    except httpx.HTTPStatusError:
                        # Skip documents that fail download
                        continue

                    yield PluginArtifact(
                        uri=f"diavgeia://{ada}",
                        data=pdf_resp.content,
                        mime=pdf_resp.headers.get(
                            "content-type", "application/pdf"
                        ),
                        meta={
                            "ada": ada,
                            "subject": item.get("subject", ""),
                            "organization": item.get("organization", ""),
                            "decisionType": item.get("decisionType", ""),
                            "protocolNumber": item.get("protocolNumber", ""),
                            "issueDate": _parse_ts(item.get("issueDate")),
                            "url": (
                                item.get("documentUrl", "")
                                or item.get("url", "")
                            ),
                        },
                    )
                    seen += 1
                    # Track last ADA for progress
                    cfg.last_ada = ada

                page += 1
                if cfg.max_pages > 0 and page >= cfg.max_pages:
                    break

                # Check if there are more pages (the API returns fewer than
                # page_size means we're done)
                if len(decisions) < cfg.page_size:
                    break

    @property
    def last_ada(self) -> str:
        """The last ADA fetched in the most recent run."""
        return self._last_ada if hasattr(self, "_last_ada") else ""


def _parse_ts(ts: int | None) -> str | None:
    """Convert a JS-style epoch-millis timestamp to ISO string, or None."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat()
    except (ValueError, OSError):
        return None


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
