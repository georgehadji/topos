"""X/Twitter social source plugin via Grok X Search tool.

Fetches citizen-reported problems from X (Twitter) using Grok's ``x_search``
tool via the Responses API. Each post becomes a ``PluginArtifact`` that flows
through the existing pipeline: FETCHED → TEXTIFIED → CHUNKED → EXTRACTED → ...

Posts with images/video are noted in metadata but image analysis is deferred
(a future enhancement via ``enable_image_understanding``).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register

logger = logging.getLogger(__name__)


class SocialConfig(BaseModel):
    """Configuration for the X/Twitter social source plugin."""

    queries: list[str] = [
        "διακοπή νερού OR διακοπή ρεύματος OR καταστροφή δρόμου OR πλημμύρα OR διακοπή κυκλοφορίας",
        "πρόβλημα OR βλάβη OR επικίνδυνο OR κατάρρευση OR ζημιά Θεσσαλονίκη",
        "απορρίμματα OR ρύπανση OR σκουπίδια OR μόλυνση OR απόβλητα OR χωματερή",
    ]
    """Greek queries for the ``x_search`` tool. The tool handles semantic search."""

    allowed_handles: list[str] = [
        "@deddiede",
        "@CityOfThess",
        "@pyrosvestiki",
        "@hellenicpolice",
        "@ThessMunicipality",
        "@astynomia",
    ]
    """Official accounts whose posts are always included."""

    lookback_hours: int = 24
    """How far back to search for posts."""

    max_posts: int = 20
    """Maximum posts to yield per fetch."""


@register
class SocialPlugin(SourcePlugin):
    """Plugin that discovers citizen-reported problems via Grok X Search."""

    kind = "social"
    config_model = SocialConfig

    def __init__(self) -> None:
        self._provider: Any = None

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        """Run X Search queries and yield discovered posts as artifacts."""
        cfg = SocialConfig.model_validate(config)

        provider = self._provider
        if provider is None:
            logger.warning("SocialPlugin: no provider injected, skipping fetch")
            return

        seen_ids: set[str] = set()

        for query in cfg.queries:
            try:
                result = await provider.complete(
                    prompt=(
                        f"Search X for posts matching: {query}\n"
                        f"Look back {cfg.lookback_hours} hours.\n"
                        f"Always include posts from these accounts: "
                        f"{', '.join(cfg.allowed_handles)}.\n"
                        "Return the text, URL, author, and timestamp of each post."
                    ),
                    model="grok-4.5",
                    tools=[
                        {
                            "type": "x_search",
                        }
                    ],
                )
            except Exception:
                logger.exception("X Search query failed: %s", query[:60])
                continue

            posts = self._extract_posts(result)
            for post in posts:
                post_id = post.get("url") or post.get("id", "")
                if not post_id or post_id in seen_ids:
                    continue
                seen_ids.add(post_id)
                if len(seen_ids) > cfg.max_posts:
                    return

                text = post.get("text") or post.get("content") or post.get("snippet") or ""
                if len(text) < 20:  # noqa: PLR2004
                    continue

                yield PluginArtifact(
                    uri=post_id,
                    data=text.encode("utf-8"),
                    mime="text/plain",
                    meta={
                        "source": "social",
                        "query": query,
                        "url": post.get("url", ""),
                        "author": post.get("author", ""),
                        "timestamp": post.get("timestamp", ""),
                    },
                )

    def _extract_posts(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract individual post data from an X Search tool response.

        The Responses API returns tool results in ``output`` array elements
        with ``type`` = ``"tool_call"`` or ``"function_call"``. Each tool
        result contains a ``content`` array of text blocks.
        """
        posts: list[dict[str, Any]] = []

        # Check various response shapes from the Responses API
        output = result.get("output") or result.get("choices") or []

        for item in output:
            if isinstance(item, dict):
                content = item.get("content") or item.get("message", {}).get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                posts.append({"text": text})
                elif isinstance(content, str) and content.strip():
                    posts.append({"text": content})

            # Tool call results
            if isinstance(item, dict) and item.get("type") in ("tool_call", "function_call"):
                response_text = item.get("response") or item.get("output", "")
                if isinstance(response_text, str) and response_text.strip():
                    posts.append({"text": response_text, "url": item.get("name", "")})

        return posts
