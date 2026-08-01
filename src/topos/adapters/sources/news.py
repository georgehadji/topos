"""Local news feeds source plugin.

Fetches articles from local Thessaloniki news sites via RSS/Atom.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register


class NewsConfig(BaseModel):
    feeds: list[str] = [
        # Verified live 2026-08-01. The trailing slash matters: /feed 301s, and
        # the client did not follow redirects, so this fetched nothing at all.
        "https://www.thestival.gr/feed/",
        "https://parallaximag.gr/feed",
    ]
    max_per_feed: int = 5


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]


@register
class NewsPlugin(SourcePlugin):
    """Plugin for local news feeds."""

    kind = "news"
    config_model = NewsConfig

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = NewsConfig.model_validate(config)

        for feed_url in cfg.feeds:
            try:
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                    resp = await client.get(
                        feed_url,
                        headers={"User-Agent": "Topos/0.1"},
                    )
                    resp.raise_for_status()
                    body = resp.text
            except httpx.HTTPStatusError:
                continue

            links = re.findall(r"<link>(https?://[^<]+)</link>", body)
            titles = re.findall(r"<title>([^<]+)</title>", body)

            # max_per_feed was parsed and never used: every item in the feed got
            # fetched sequentially at a 30s timeout, so a 50-entry feed could
            # block for many minutes. Bound the work before doing any of it.
            for url, title in list(zip(links, titles, strict=False))[: cfg.max_per_feed]:
                try:
                    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c2:
                        art = await c2.get(
                            url,
                            headers={"User-Agent": "Topos/0.1"},
                        )
                        art.raise_for_status()
                except httpx.HTTPStatusError:
                    continue

                text = _strip_html(art.text)
                if len(text) < 100:  # noqa: PLR2004
                    continue

                yield PluginArtifact(
                    uri=f"news://{url.split('/')[-1] or 'article'}",
                    data=text.encode("utf-8"),
                    mime="text/plain",
                    meta={"url": url, "title": title, "source": feed_url},
                )
