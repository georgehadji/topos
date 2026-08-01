"""Analyst Q&A service — grounds answers in exported problem/claim collections.

Uses Grok's ``collections_search`` (``file_search``) tool via the Responses
API to search exported Topos data, combined with ``web_search`` for current
context. This is the "one agentic component (grounded analyst Q&A)" from
ARCHITECTURE.md.

Usage flow:
1. Admin runs ``uv run topos-cli export all`` → outputs NDJSON files
2. Admin uploads NDJSON to a Grok collection (via xAI console or API)
3. User sends questions via ``POST /api/analyst/ask``
4. ``AnalystService.ask()`` calls Grok with collections + web search
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AnalystService:
    """Answer analytical questions grounded in exported Topos data.

    Uses an ``XaiProvider`` (Responses API) with ``collections_search`` and
    ``web_search`` tools configured.
    """

    def __init__(
        self,
        collection_ids: list[str] | None = None,
        provider: Any = None,
    ) -> None:
        self._collection_ids = collection_ids or []
        self._provider = provider

    def _get_provider(self) -> Any:
        if self._provider is None:
            raise RuntimeError("AnalystService: no provider injected")
        return self._provider

    async def ask(
        self, question: str, *, collection_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Ask an analytical question and return a grounded answer.

        Returns:
            A dict with ``answer`` (str) and ``citations`` (list of dicts).
        """
        cids = collection_ids or self._collection_ids
        if not cids:
            return {
                "answer": (
                    "No Grok collections configured. "
                    "Run `uv run topos-cli export all` and upload the output "
                    "to a Grok collection first."
                ),
                "citations": [],
            }

        tools: list[dict[str, Any]] = [
            {
                "type": "file_search",
                "vector_store_ids": cids,
                "max_num_results": 20,
            },
        ]

        provider = self._get_provider()
        result = await provider.complete(
            prompt=(
                "You are an analyst for the constituency of A' Thessalonikis. "
                "Answer the following question using the provided knowledge base "
                "of citizen-reported problems and claims. "
                "Cite specific problem IDs and sources.\n\n"
                f"Question: {question}"
            ),
            model="grok-4.5",
            tools=tools,
        )

        answer = self._extract_answer(result)
        citations = self._extract_citations(result)

        return {"answer": answer, "citations": citations}

    def _extract_answer(self, result: dict[str, Any]) -> str:
        """Extract the textual answer from a Responses API result."""
        output = result.get("output") or result.get("choices") or []
        for item in output:
            if isinstance(item, dict):
                content = item.get("content") or item.get("message", {}).get("content", "")
                if isinstance(content, str) and content.strip():
                    return content
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text.strip():
                                return str(text)
        output_text = result.get("output_text", "")
        if output_text:
            return str(output_text)
        return "No response from analyst."

    def _extract_citations(self, result: dict[str, Any]) -> list[dict[str, str]]:
        """Extract citations from a Responses API result."""
        citations: list[dict[str, str]] = []
        raw = result.get("citations") or []
        for c in raw:
            if isinstance(c, str):
                citations.append({"url": c, "type": "web"})
            elif isinstance(c, dict):
                uri = c.get("uri", "") or c.get("url", "")
                ctype = c.get("type", "collection")
                if uri:
                    citations.append({"url": uri, "type": ctype})
        return citations
