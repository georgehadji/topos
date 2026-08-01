"""Unit tests for AnalystService — mock provider, verify query flow."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from topos.service.analyst import AnalystService


class MockAnalystProvider:
    """Mock XaiProvider returning canned Responses API results."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        prompt: str,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "prompt_preview": prompt[:80],
                "tools": tools,
                "kwargs": kwargs,
            }
        )
        return self.response


_SAMPLE_RESPONSE = {
    "output": [
        {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Based on the problem database, the highest-priority "
                        "unresolved infrastructure issue in Kalamaria is a "
                        "water main break on Egnatia street (problem_id: "
                        "abc-123). It has been open for 14 days and affects "
                        "approximately 200 households."
                    ),
                }
            ]
        }
    ],
    "citations": [
        "collections://collection_xyz/files/file_001",
        {"uri": "https://voria.gr/article/water-main", "type": "web"},
    ],
}


def test_analyst_service_ask_returns_structured_answer() -> None:
    """AnalystService.ask() returns answer + citations from provider."""
    service = AnalystService(collection_ids=["collection_xyz"])
    service._provider = MockAnalystProvider(_SAMPLE_RESPONSE)

    result = asyncio.run(service.ask("What are the top problems in Kalamaria?"))

    assert "water main break" in result["answer"]
    assert len(result["citations"]) == 2
    assert result["citations"][0]["url"].startswith("collections://")
    assert result["citations"][1]["url"].startswith("https://")


def test_analyst_service_no_collections_returns_helpful_message() -> None:
    """Without configured collections, service returns setup instructions."""
    service = AnalystService()
    service._provider = MockAnalystProvider(_SAMPLE_RESPONSE)

    result = asyncio.run(service.ask("What are the top problems?"))

    assert "Run `uv run topos-cli export all" in result["answer"]
    assert result["citations"] == []


def test_analyst_service_sends_file_search_tool() -> None:
    """Provider is called with file_search tool containing collection IDs."""
    provider = MockAnalystProvider(_SAMPLE_RESPONSE)
    service = AnalystService(collection_ids=["collection_abc", "collection_def"])
    service._provider = provider

    asyncio.run(service.ask("Problems near Egnatia street?"))

    assert len(provider.calls) == 1
    tools = provider.calls[0]["tools"]
    assert len(tools) == 1
    assert tools[0]["type"] == "file_search"
    assert tools[0]["vector_store_ids"] == ["collection_abc", "collection_def"]


@pytest.mark.asyncio
async def test_analyst_service_extracts_text_from_output_text_field() -> None:
    """When output_text is present, use it as the answer."""
    service = AnalystService(collection_ids=["collection_x"])
    service._provider = MockAnalystProvider(
        {
            "output_text": "Direct text output from API.",
            "citations": [],
        }
    )

    result = await service.ask("Test?")
    assert result["answer"] == "Direct text output from API."
