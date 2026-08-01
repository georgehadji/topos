# ruff: noqa: RUF002
"""Web search source — one plugin, several engines.

Each engine is a plain HTTPS call, no vendor SDKs. An engine is *available*
when its key (or base URL, for self-hosted SearXNG) is configured; with
``engine="auto"`` every available engine is queried and results are merged and
deduplicated by URL, so adding a key widens coverage without a code change.

Keys come from Settings, never from ``source.config`` — that column is stored
in Postgres and read back by the API, and secrets do not belong there.

See ARCHITECTURE.md §Greek: queries are Greek by default, because the sources
that matter for Α΄ Θεσσαλονίκης are Greek-language.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register
from topos.config import Settings, get_settings

logger = logging.getLogger(__name__)

# (url, title, snippet)
Hit = tuple[str, str, str]

_TIMEOUT = 30
_UA = "Topos/0.1 (constituency intelligence; contact@topos.local)"


class WebSearchConfig(BaseModel):
    """Config stored in source.config jsonb. Contains no secrets."""

    engine: str = "auto"
    """``auto`` queries every engine that has credentials configured.
    Otherwise one of: brave, google_cse, bing, tavily, serper, searxng."""

    queries: list[str] = [
        "διακοπή νερού Θεσσαλονίκη",
        "διακοπή ρεύματος Θεσσαλονίκη",
        "λακκούβες δρόμος Θεσσαλονίκη",
        "πλημμύρα Θεσσαλονίκη",
        "σκουπίδια απορρίμματα Θεσσαλονίκη",
    ]

    max_results: int = 20
    """Cap on artifacts yielded per fetch, across all engines and queries."""

    per_query: int = 10
    """Results requested from each engine per query."""

    lang: str = "el"
    country: str = "gr"
    freshness_days: int = 30


# ── Engines ──────────────────────────────────────────────────────────────────
# Each returns (url, title, snippet) triples. Raising is fine: fetch() isolates
# every engine call, logs, and carries on with the others.


async def _brave(c: httpx.AsyncClient, s: Settings, q: str, cfg: WebSearchConfig) -> list[Hit]:
    r = await c.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={
            "q": q,
            "count": cfg.per_query,
            "search_lang": cfg.lang,
            "country": cfg.country,
        },
        headers={"Accept": "application/json", "X-Subscription-Token": s.brave_api_key},
    )
    r.raise_for_status()
    results = r.json().get("web", {}).get("results", [])
    return [(x.get("url", ""), x.get("title", ""), x.get("description", "")) for x in results]


async def _google_cse(c: httpx.AsyncClient, s: Settings, q: str, cfg: WebSearchConfig) -> list[Hit]:
    r = await c.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": s.google_cse_api_key,
            "cx": s.google_cse_cx,
            "q": q,
            "num": min(cfg.per_query, 10),  # API hard limit
            "hl": cfg.lang,
            "gl": cfg.country,
        },
    )
    r.raise_for_status()
    return [
        (x.get("link", ""), x.get("title", ""), x.get("snippet", ""))
        for x in r.json().get("items", [])
    ]


async def _bing(c: httpx.AsyncClient, s: Settings, q: str, cfg: WebSearchConfig) -> list[Hit]:
    r = await c.get(
        "https://api.bing.microsoft.com/v7.0/search",
        params={
            "q": q,
            "count": cfg.per_query,
            "mkt": f"{cfg.lang}-{cfg.country.upper()}",
        },
        headers={"Ocp-Apim-Subscription-Key": s.bing_api_key},
    )
    r.raise_for_status()
    values = r.json().get("webPages", {}).get("value", [])
    return [(x.get("url", ""), x.get("name", ""), x.get("snippet", "")) for x in values]


async def _tavily(c: httpx.AsyncClient, s: Settings, q: str, cfg: WebSearchConfig) -> list[Hit]:
    r = await c.post(
        "https://api.tavily.com/search",
        json={
            "api_key": s.tavily_api_key,
            "query": q,
            "max_results": cfg.per_query,
            "search_depth": "basic",
            "days": cfg.freshness_days,
        },
    )
    r.raise_for_status()
    return [
        (x.get("url", ""), x.get("title", ""), x.get("content", ""))
        for x in r.json().get("results", [])
    ]


async def _serper(c: httpx.AsyncClient, s: Settings, q: str, cfg: WebSearchConfig) -> list[Hit]:
    r = await c.post(
        "https://google.serper.dev/search",
        json={"q": q, "num": cfg.per_query, "hl": cfg.lang, "gl": cfg.country},
        headers={"X-API-KEY": s.serper_api_key, "Content-Type": "application/json"},
    )
    r.raise_for_status()
    return [
        (x.get("link", ""), x.get("title", ""), x.get("snippet", ""))
        for x in r.json().get("organic", [])
    ]


async def _searxng(c: httpx.AsyncClient, s: Settings, q: str, cfg: WebSearchConfig) -> list[Hit]:
    r = await c.get(
        f"{s.searxng_base_url.rstrip('/')}/search",
        params={"q": q, "format": "json", "language": cfg.lang},
    )
    r.raise_for_status()
    results = r.json().get("results", [])[: cfg.per_query]
    return [(x.get("url", ""), x.get("title", ""), x.get("content", "")) for x in results]


EngineFn = Callable[[httpx.AsyncClient, Settings, str, WebSearchConfig], Coroutine[Any, Any, Any]]

# engine name -> (call, "is it configured?")
_ENGINES: dict[str, tuple[EngineFn, Callable[[Settings], bool]]] = {
    "brave": (_brave, lambda s: bool(s.brave_api_key)),
    "google_cse": (_google_cse, lambda s: bool(s.google_cse_api_key and s.google_cse_cx)),
    "bing": (_bing, lambda s: bool(s.bing_api_key)),
    "tavily": (_tavily, lambda s: bool(s.tavily_api_key)),
    "serper": (_serper, lambda s: bool(s.serper_api_key)),
    "searxng": (_searxng, lambda s: bool(s.searxng_base_url)),
}


def available_engines(settings: Settings | None = None) -> list[str]:
    """Engine names that currently have credentials configured."""
    s = settings or get_settings()
    return [name for name, (_, configured) in _ENGINES.items() if configured(s)]


@register
class WebSearchPlugin(SourcePlugin):
    """Discovers problem reports through general-purpose web search engines."""

    kind = "websearch"
    config_model = WebSearchConfig

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        """Query every selected engine and yield each unique URL once."""
        cfg = WebSearchConfig.model_validate(config)
        s = self._settings or get_settings()

        if cfg.engine == "auto":
            engines = available_engines(s)
        elif cfg.engine in _ENGINES and _ENGINES[cfg.engine][1](s):
            engines = [cfg.engine]
        else:
            engines = []

        if not engines:
            logger.warning(
                "WebSearchPlugin: no engine configured for %r. Set one of: %s",
                cfg.engine,
                ", ".join(sorted(_ENGINES)),
            )
            return

        logger.info("WebSearchPlugin: querying %s", ", ".join(engines))
        seen: set[str] = set()

        async with httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            for query in cfg.queries:
                for name in engines:
                    call, _ = _ENGINES[name]
                    try:
                        hits = await call(client, s, query, cfg)
                    except Exception:
                        # One engine failing must not stop the others.
                        logger.exception("websearch %s failed for %r", name, query[:60])
                        continue

                    for url, title, snippet in hits:
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        if len(seen) > cfg.max_results:
                            return

                        text = "\n".join(p for p in (title, snippet) if p) or url
                        yield PluginArtifact(
                            uri=url,
                            data=text.encode("utf-8"),
                            mime="text/plain",
                            meta={
                                "source": "websearch",
                                "engine": name,
                                "query": query,
                                "url": url,
                                "title": title,
                            },
                        )
