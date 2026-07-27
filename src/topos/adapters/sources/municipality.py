"""Municipality of Thessaloniki source plugin.

Fetches announcements from the municipality website via RSS.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register


class MunicipalityConfig(BaseModel):
    feed_url: str = "https://thessaloniki.gr/feed/"
    max_items: int = 10


@register
class MunicipalityPlugin(SourcePlugin):
    """Plugin for thessaloniki.gr — municipal announcements."""

    kind = "municipality"
    config_model = MunicipalityConfig

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = MunicipalityConfig.model_validate(config)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(
                cfg.feed_url,
                headers={"User-Agent": "Topos/0.1"},
            )
            resp.raise_for_status()
            body = resp.text

        pdf_urls = re.findall(
            r"(https?://[^\s\"']+\.pdf)",
            body,
            re.IGNORECASE,
        )
        link_urls = re.findall(r"<link[^>]*href=\"([^\"]*)\"", body)
        urls = list(dict.fromkeys(pdf_urls + link_urls))[: cfg.max_items]

        for i, url in enumerate(urls):
            try:
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c2:
                    doc_resp = await c2.get(url)
                    doc_resp.raise_for_status()
                    yield PluginArtifact(
                        uri=f"municipality://{url.split('/')[-1] or str(i)}",
                        data=doc_resp.content,
                        mime=doc_resp.headers.get("content-type", "application/octet-stream"),
                        meta={"url": url, "source": "thessaloniki.gr"},
                    )
            except httpx.HTTPStatusError:
                continue
