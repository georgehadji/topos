"""Shared reranker construction for interfaces/ (http, mcp, cli).

interfaces/ is the only layer allowed to pick a concrete adapter
(.importlinter contract service-ports-only) — this is that choice made once,
not copy-pasted at each of the three call sites that need it.
"""

from __future__ import annotations

from topos.adapters.rerank import OpenRouterReranker
from topos.config import Settings, is_placeholder_key


def build_reranker(settings: Settings) -> OpenRouterReranker | None:
    """None when reranking is disabled or no usable key is configured.

    A None reranker is not an error anywhere that consumes it — search_repo.py
    just runs the lexical pass unranked (see SearchRepo._rerank's fail-open
    behavior for the same tolerance at call time, not just at construction).
    """
    if not settings.rerank_enabled or is_placeholder_key(settings.llm_api_key):
        return None
    models = [m.strip() for m in settings.rerank_models.split(",") if m.strip()]
    if not models:
        return None
    return OpenRouterReranker(
        api_key=settings.llm_api_key, base_url=settings.llm_base_url, models=models
    )
