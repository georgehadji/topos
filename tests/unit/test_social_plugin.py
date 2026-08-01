"""Unit tests for SocialPlugin — mock XaiProvider, verify artifact extraction."""

from __future__ import annotations

from typing import Any

import pytest

from topos.adapters.sources.social import SocialConfig, SocialPlugin


class DummyXSearchProvider:
    """Mock XaiProvider returning canned X Search responses."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(prompt[:100])
        if self.responses:
            return self.responses.pop(0)
        return {"output": []}


_SAMPLE_RESPONSE = {
    "output": [
        {
            "type": "tool_call",
            "name": "x_search",
            "response": (
                "- **Post by @resident:** Διακοπή ρεύματος στην περιοχή της Τούμπας "
                "εδώ και 3 ώρες. Κανείς δεν έχει ενημερώσει. [#Thessaloniki]"
            ),
        }
    ]
}


@pytest.mark.asyncio
async def test_fetch_yields_artifacts_from_x_search() -> None:
    """Plugin yields one PluginArtifact per X post found."""
    plugin = SocialPlugin()
    config = SocialConfig(
        queries=["Test query"],
        lookback_hours=24,
        max_posts=10,
    )

    provider = DummyXSearchProvider([_SAMPLE_RESPONSE])
    plugin._provider = provider

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) >= 1
    meta = artifacts[0].meta
    assert meta is not None
    assert meta["source"] == "social"


@pytest.mark.asyncio
async def test_fetch_respects_max_posts() -> None:
    """Plugin stops yielding after max_posts is reached."""
    plugin = SocialPlugin()
    config = SocialConfig(
        queries=["Query with many results"],
        lookback_hours=24,
        max_posts=3,
    )

    response = {
        "output": [
            {
                "type": "tool_call",
                "name": "x_search",
                "response": "\n".join(f"- **Post {i}:** Test post content #{i}" for i in range(10)),
            }
        ]
    }

    provider = DummyXSearchProvider([response])
    plugin._provider = provider

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) <= 3


@pytest.mark.asyncio
async def test_fetch_handles_empty_response() -> None:
    """Plugin handles empty X Search response."""
    plugin = SocialPlugin()
    config = SocialConfig(
        queries=["Query with no results"],
        lookback_hours=24,
        max_posts=10,
    )

    provider = DummyXSearchProvider([{"output": []}])
    plugin._provider = provider

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) == 0


@pytest.mark.asyncio
async def test_fetch_skips_short_posts() -> None:
    """Plugin skips posts shorter than 20 characters."""
    plugin = SocialPlugin()
    config = SocialConfig(
        queries=["Short posts test"],
        lookback_hours=24,
        max_posts=10,
    )

    response = {
        "output": [
            {
                "type": "tool_call",
                "name": "x_search",
                "response": "- **@user:** Hi\n- **@user2:** This is a longer post about a real problem in Thessaloniki",
            }
        ]
    }

    provider = DummyXSearchProvider([response])
    plugin._provider = provider

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) == 1
    assert "longer post" in artifacts[0].data.decode("utf-8")


@pytest.mark.asyncio
async def test_fetch_logs_on_provider_error() -> None:
    """When X Search call fails, plugin logs and continues to next query."""
    plugin = SocialPlugin()
    config = SocialConfig(
        queries=["Query one", "Query two"],
        lookback_hours=24,
        max_posts=10,
    )

    class FailingProvider:
        async def complete(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("X API timeout")

    plugin._provider = FailingProvider()

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) == 0


@pytest.mark.asyncio
async def test_fetch_deduplicates_posts() -> None:
    """Same post URL appearing in multiple queries is yielded once."""
    plugin = SocialPlugin()
    config = SocialConfig(
        queries=["First query", "Second query"],
        lookback_hours=24,
        max_posts=10,
    )

    # Same tool_call name across queries = same post
    response1 = {
        "output": [
            {
                "type": "tool_call",
                "name": "https://x.com/user/status/1",
                "response": "Power outage in Kalamaria since this morning",
            }
        ]
    }
    response2 = {
        "output": [
            {
                "type": "tool_call",
                "name": "https://x.com/user/status/1",
                "response": "Power outage in Kalamaria",
            }
        ]
    }

    provider = DummyXSearchProvider([response1, response2])
    plugin._provider = provider

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    # Both queries returned the same URL — should only be yielded once
    assert len(artifacts) == 1
    assert len(provider.calls) == 2  # both queries ran
