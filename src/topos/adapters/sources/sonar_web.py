"""Sonar web discovery source plugin.

Uses Perplexity Sonar (via OpenRouter) to discover citizen-affecting problems
on Greek websites not covered by the existing source plugins.

The plugin queries Sonar with Greek-language prompts, receives cited search
results, and yields each unique URL as a ``PluginArtifact``. The pipeline then
processes these normally — ``FETCHED → TEXTIFIED → CHUNKED → EXTRACTED → ...``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register

logger = logging.getLogger(__name__)


class SonarWebConfig(BaseModel):
    """Configuration for the Sonar web discovery plugin."""

    queries: list[str] = [
        "What infrastructure problems (road damage, water outages, power cuts, "
        "flooding, public transport failures) were reported in Θεσσαλονίκη "
        "or Thessaloniki municipality this week?",
        "What health, safety, or environmental problems (pollution, waste, "
        "green space damage) were reported in Θεσσαλονίκη this week?",
        "What administrative or social issues (delays, missing services, "
        "bureaucratic failures, housing, education) were reported in "
        "Θεσσαλονίκη this week?",
    ]
    """Greek/English query strings sent to Sonar. The user message drives search."""

    domains: list[str] = [
        "thessaloniki.gr",
        "voria.gr",
        "typosthes.gr",
        "parallaximag.gr",
        "thessnews.gr",
        "makthes.gr",
    ]
    """Trusted Greek domains to restrict search results to."""

    recency: str = "week"
    """Sonar ``search_recency_filter`` — ``day``, ``week``, or ``month``."""

    max_results: int = 10
    """Maximum citations to yield per query."""


_SYSTEM_PROMPT = (
    "Only answer using the search results provided. "
    "If the results do not contain the answer, say so explicitly rather than guessing. "
    "If the search results are related but do not match the question, "
    "state the mismatch explicitly before answering."
)


@register
class SonarWebPlugin(SourcePlugin):
    """Plugin that discovers problems via Perplexity Sonar web search."""

    kind = "sonar_web"
    config_model = SonarWebConfig

    def __init__(self, provider: Any = None) -> None:
        self._provider = provider

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        """Run Sonar queries and yield discovered URLs as artifacts."""
        cfg = SonarWebConfig.model_validate(config)

        # Build kwargs that filter the Sonar search.
        search_kwargs: dict[str, Any] = {
            "search_domain_filter": cfg.domains,
            "search_recency_filter": cfg.recency,
        }

        # Use pre-set provider (injected by caller or tests).
        if self._provider is None:
            logger.warning("SonarWebPlugin: no provider injected, skipping fetch")
            return

        seen_urls: set[str] = set()

        for query in cfg.queries:
            try:
                result = await self._provider.complete(
                    prompt=f"{_SYSTEM_PROMPT}\n\n{query}",
                    model="perplexity/sonar-pro",
                    **search_kwargs,
                )
            except Exception:
                logger.exception("Sonar query failed: %s", query[:80])
                continue

            citations = self._extract_citations(result)
            for url, title, snippet in citations:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                if len(seen_urls) > cfg.max_results:
                    return

                yield PluginArtifact(
                    uri=url,
                    data=(snippet or title or url).encode("utf-8"),
                    mime="text/plain",
                    meta={
                        "source": "sonar_web",
                        "query": query,
                        "url": url,
                        "title": title or "",
                    },
                )

    def _extract_citations(
        self,
        result: dict[str, Any],
    ) -> list[tuple[str, str, str]]:
        """Extract ``(url, title, snippet)`` tuples from a Sonar response.

        Sonar returns citations in the top-level ``citations`` and
        ``search_results`` fields. We prefer ``search_results`` for richer
        metadata and fall back to ``citations`` (which are bare URLs).
        """
        extracted: list[tuple[str, str, str]] = []

        # search_results has richer metadata
        for sr in result.get("search_results") or []:
            if not isinstance(sr, dict):
                continue
            url = (sr.get("url") or "").strip()
            title = (sr.get("title") or "").strip()
            snippet = (sr.get("snippet") or "").strip()
            if url:
                extracted.append((url, title, snippet))

        # citations are bare URLs — use as fallback
        raw_citations = result.get("citations") or []
        for c in raw_citations:
            if isinstance(c, str) and c.strip():
                url = c.strip()
                if url not in {e[0] for e in extracted}:
                    extracted.append((url, "", ""))

        return extracted
