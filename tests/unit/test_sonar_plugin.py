"""Unit tests for SonarWebPlugin — mock SonarProvider, verify artifact extraction."""

from __future__ import annotations

from typing import Any

import pytest

from topos.adapters.sources.sonar_web import SonarWebConfig, SonarWebPlugin


class DummySonarProvider:
    """Mock SonarProvider returning canned responses."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(prompt[:100])
        if self.responses:
            return self.responses.pop(0)
        return {"choices": [], "citations": [], "search_results": []}


@pytest.mark.asyncio
async def test_fetch_yields_artifacts_from_search_results() -> None:
    """Plugin yields one PluginArtifact per search result URL."""
    plugin = SonarWebPlugin()
    config = SonarWebConfig(
        queries=["What problems in Thessaloniki this week?"],
        recency="week",
        max_results=5,
    )

    # Canned Sonar response with search_results
    plugin._provider = DummySonarProvider(
        [
            {
                "choices": [{"message": {"content": "Some answer about problems."}}],
                "search_results": [
                    {
                        "url": "https://voria.gr/article/test-1",
                        "title": "Road damage in center",
                        "snippet": "A large pothole on Egnatia street...",
                    },
                    {
                        "url": "https://typosthes.gr/article/test-2",
                        "title": "Water outage in Kalamaria",
                        "snippet": "Residents without water...",
                    },
                ],
                "citations": [
                    "https://voria.gr/article/test-1",
                    "https://typosthes.gr/article/test-2",
                ],
            },
        ]
    )

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) == 2
    assert artifacts[0].uri == "https://voria.gr/article/test-1"
    assert artifacts[0].meta is not None
    assert artifacts[0].meta["title"] == "Road damage in center"
    assert artifacts[1].uri == "https://typosthes.gr/article/test-2"
    assert artifacts[1].meta is not None
    assert artifacts[1].meta["source"] == "sonar_web"


@pytest.mark.asyncio
async def test_fetch_deduplicates_urls() -> None:
    """Same URL appearing in both search_results and citations is yielded once."""
    plugin = SonarWebPlugin()
    config = SonarWebConfig(
        queries=["Test query"],
        recency="week",
        max_results=5,
    )

    plugin._provider = DummySonarProvider(
        [
            {
                "choices": [{"message": {"content": "Answer."}}],
                "search_results": [
                    {
                        "url": "https://voria.gr/article/dupe",
                        "title": "Duplicate",
                        "snippet": "Same URL appears below in citations.",
                    },
                ],
                "citations": [
                    "https://voria.gr/article/dupe",
                    "https://typosthes.gr/article/other",
                ],
            },
        ]
    )

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) == 2
    uris = {a.uri for a in artifacts}
    assert uris == {
        "https://voria.gr/article/dupe",
        "https://typosthes.gr/article/other",
    }


@pytest.mark.asyncio
async def test_fetch_respects_max_results() -> None:
    """Plugin stops yielding after max_results is reached."""
    plugin = SonarWebPlugin()
    config = SonarWebConfig(
        queries=["Test query"],
        recency="week",
        max_results=2,
    )

    # Return 4 results — should only get 2
    plugin._provider = DummySonarProvider(
        [
            {
                "choices": [{"message": {"content": "Answer."}}],
                "search_results": [
                    {"url": f"https://voria.gr/article/{i}", "title": f"Article {i}", "snippet": ""}
                    for i in range(4)
                ],
                "citations": [],
            },
        ]
    )

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) == 2


@pytest.mark.asyncio
async def test_fetch_handles_empty_response() -> None:
    """Plugin handles an empty Sonar response gracefully."""
    plugin = SonarWebPlugin()
    config = SonarWebConfig(
        queries=["Empty query"],
        recency="week",
        max_results=10,
    )

    plugin._provider = DummySonarProvider(
        [
            {
                "choices": [{"message": {"content": "No results found."}}],
                "search_results": [],
                "citations": [],
            },
        ]
    )

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) == 0


@pytest.mark.asyncio
async def test_fetch_skips_malformed_search_results() -> None:
    """Plugin skips entries in search_results that have no URL."""
    plugin = SonarWebPlugin()
    config = SonarWebConfig(
        queries=["Test query"],
        recency="week",
        max_results=10,
    )

    plugin._provider = DummySonarProvider(
        [
            {
                "choices": [{"message": {"content": "Answer."}}],
                "search_results": [
                    {"url": "", "title": "No URL", "snippet": "skipped"},
                    {"url": "https://voria.gr/article/valid", "title": "Valid", "snippet": "ok"},
                    {},  # completely empty dict
                ],
                "citations": [],
            },
        ]
    )

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) == 1
    assert artifacts[0].uri == "https://voria.gr/article/valid"


@pytest.mark.asyncio
async def test_fetch_logs_on_provider_error() -> None:
    """When Sonar call fails, plugin logs error and continues to next query."""
    plugin = SonarWebPlugin()
    config = SonarWebConfig(
        queries=["Query one", "Query two"],
        recency="week",
        max_results=10,
    )

    class FailingProvider:
        async def complete(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("API timeout")

    plugin._provider = FailingProvider()

    artifacts = []
    async for artifact in plugin.fetch(config):
        artifacts.append(artifact)

    assert len(artifacts) == 0
