"""Shared fetcher for RSS/Atom and WordPress-REST civic feeds.

Most Greek public bodies publish announcements the same two ways: a WordPress
`/feed/` and a `/wp-json/wp/v2/posts` REST endpoint behind it. Subclasses
below declare only a ``kind`` and default feed URLs; the fetching, HTML
stripping and bounding live here once.

Prefer the REST endpoint where a site exposes it: it returns structured JSON
with real timestamps and post ids, where RSS has to be regex-scraped. `fetch`
takes whichever the config names.

Two lessons from probing these hosts (2026-08-04) are encoded here:

* **The trailing slash matters.** `/feed` 301s to `/feed/`; without redirect
  following that fetched nothing. `follow_redirects=True` everywhere.
* **Content-Type lies.** Several of these hosts serve valid RSS as
  `text/html` and valid JSON as `text/html`. Never branch on the header —
  branch on what the body actually parses as.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Topos/0.1"}
_MIN_TEXT = 80


class FeedConfig(BaseModel):
    """Feed URLs plus a per-feed cap. Subclasses override the defaults."""

    feeds: list[str] = []
    max_per_feed: int = 10


def strip_html(html: str, *, limit: int = 4000) -> str:
    """Tags out, entities decoded, whitespace collapsed."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    for entity, char in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#8217;", "'"),
        ("&#8211;", "-"),
    ):
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _wp_items(body: str, limit: int) -> list[tuple[str, str, str]]:
    """(uri_hint, title, text) from a wp-json posts array, or [] if not JSON."""
    try:
        posts = json.loads(body)
    except (ValueError, TypeError):
        return []
    if not isinstance(posts, list):
        return []

    out: list[tuple[str, str, str]] = []
    for post in posts[:limit]:
        if not isinstance(post, dict):
            continue
        title = strip_html(str(_nested(post, "title")), limit=300)
        body_text = strip_html(str(_nested(post, "content")))
        excerpt = strip_html(str(_nested(post, "excerpt")))
        text = f"{title}. {body_text or excerpt}".strip()
        slug = str(post.get("slug") or post.get("id") or len(out))
        out.append((slug, title, text))
    return out


def _nested(post: dict[str, Any], key: str) -> str:
    """WP returns {"title": {"rendered": "..."}} — reach through it."""
    value = post.get(key)
    if isinstance(value, dict):
        return str(value.get("rendered", ""))
    return str(value or "")


def _rss_items(body: str, limit: int) -> list[tuple[str, str, str]]:
    """(uri_hint, title, text) from RSS/Atom <item> blocks."""
    out: list[tuple[str, str, str]] = []
    for block in re.findall(r"(?is)<(?:item|entry)\b.*?</(?:item|entry)>", body)[:limit]:
        title_m = re.search(r"(?is)<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block)
        link_m = re.search(r"(?is)<link[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block)
        desc_m = re.search(
            r"(?is)<(?:description|content:encoded|summary)[^>]*>"
            r"(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</(?:description|content:encoded|summary)>",
            block,
        )
        title = strip_html(title_m.group(1), limit=300) if title_m else ""
        desc = strip_html(desc_m.group(1)) if desc_m else ""
        link = (link_m.group(1).strip() if link_m else "") or title
        text = f"{title}. {desc}".strip()
        out.append((link.rstrip("/").split("/")[-1] or "item", title, text))
    return out


class FeedPlugin(SourcePlugin):
    """Fetch announcements from a list of RSS or wp-json feeds.

    Subclasses set ``kind`` and ``config_model`` (a FeedConfig subclass whose
    ``feeds`` default names the real URLs).
    """

    kind: ClassVar[str]
    config_model: ClassVar[type[BaseModel]]
    # Prefix for artifact URIs; defaults to ``kind`` when unset.
    uri_scheme: ClassVar[str] = ""

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = self.config_model.model_validate(config)
        feeds = list(getattr(cfg, "feeds", []))
        limit = int(getattr(cfg, "max_per_feed", 10))
        scheme = self.uri_scheme or self.kind

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=_UA) as client:
            for feed_url in feeds:
                try:
                    resp = await client.get(feed_url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    # One dead feed must not kill the other six.
                    logger.warning("%s.feed_failed url=%s err=%s", self.kind, feed_url, exc)
                    continue

                body = resp.text
                items = _wp_items(body, limit) or _rss_items(body, limit)
                if not items:
                    logger.warning("%s.feed_empty url=%s", self.kind, feed_url)
                    continue

                for hint, title, text in items:
                    if len(text) < _MIN_TEXT:
                        continue
                    yield PluginArtifact(
                        uri=f"{scheme}://{hint}",
                        data=text.encode("utf-8"),
                        mime="text/plain",
                        meta={"title": title, "feed": feed_url},
                    )
