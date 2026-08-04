"""Transport disruption sources that publish no feed at all.

Both plugins here scrape HTML because the operators expose nothing better.
That is stated plainly rather than dressed up: these are the most brittle
sources in the system and will break on a site redesign. Each fails closed —
a layout change yields zero artifacts and a warning, never a fabricated one.

Not implemented, and why:

* **ΟΑΣΘ telematics** (``telematics.oasth.gr/api/?act=…``) — the arrivals API
  is alive but session-gated: it needs a ``PHPSESSID`` and CSRF token
  harvested by loading the site in a real browser, and the bootstrap page
  returns 403 to non-browser clients. Two independent probes disagreed about
  whether ``act=getNews`` is reachable with only a ``Referer`` header, so the
  access model is unsettled. Wiring this needs a headless browser and one
  decisive re-probe first.
* **GTFS** (data.gov.gr, 9 MB, 351 bus routes) — real, official and
  anonymous, but it is a *schedule*, not an incident feed. Feeding timetables
  to a problem extractor would produce nothing true. Its natural use is
  enriching the gazetteer with stop and route geometry, the way
  ``gazetteer.json`` was built from OSM.
* **GTFS-Realtime** — does not exist for Thessaloniki. MobilityData lists no
  live feed anywhere in Greece; the one indexed Thessaloniki entry is
  mainline rail, marked inactive, and its download host is shut down.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.feedbase import strip_html
from topos.adapters.sources.registry import register

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Topos/0.1"}
_MIN_TEXT = 60


class OsethConfig(BaseModel):
    """ΟΣΕΘ replaced ΟΑΣΘ as the transit authority and publishes no usable
    feed — its ``rss.xml`` carries a single item from 2024. The announcement
    and route-modification indexes are ordinary Drupal listing pages."""

    index_urls: list[str] = [
        "https://oseth.com.gr/el/nea-anakoinoseis",
        "https://oseth.com.gr/el/tropopoiiseis-diktyoy",
    ]
    max_per_index: int = 10


@register
class OsethPlugin(SourcePlugin):
    """ΟΣΕΘ — bus network notices and route modifications."""

    kind = "oseth"
    config_model = OsethConfig

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = OsethConfig.model_validate(config)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=_UA) as client:
            for index_url in cfg.index_urls:
                try:
                    resp = await client.get(index_url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("oseth.index_failed url=%s err=%s", index_url, exc)
                    continue

                links = _article_links(resp.text, base="https://oseth.com.gr")
                if not links:
                    logger.warning("oseth.no_links url=%s", index_url)

                for link in links[: cfg.max_per_index]:
                    try:
                        article = await client.get(link)
                        article.raise_for_status()
                    except httpx.HTTPError:
                        continue

                    text = strip_html(_main_content(article.text))
                    if len(text) < _MIN_TEXT:
                        continue
                    yield PluginArtifact(
                        uri=f"oseth://{link.rstrip('/').split('/')[-1]}",
                        data=text.encode("utf-8"),
                        mime="text/plain",
                        meta={"url": link, "index": index_url},
                    )


def _main_content(html: str) -> str:
    """The <article> body, or the whole page if the site has no <article>.

    Drupal renders every page inside the same shell — masthead, search box,
    "Main navigation", footer. Stripping the full document put that chrome at
    the front of every artifact, so the first thing the extractor read was a
    nav menu. Narrowing to <article> drops it.
    """
    match = re.search(r"(?is)<article\b.*?</article>", html)
    return match.group(0) if match else html


def _article_links(html: str, *, base: str) -> list[str]:
    """Absolute links to article permalinks on a Drupal index page.

    ΟΣΕΘ publishes announcements at ``/el/article/<slug>``. The index also
    carries ~45 navigation links (fares, route search, org chart) at
    ``/el/<slug>``; requiring the ``/article/`` segment separates them
    exactly, where a path-depth heuristic only approximately did.
    """
    hrefs = re.findall(r'href="(/[a-z]{2}/article/[^"#?]+)"', html)
    seen: dict[str, None] = {}
    for href in hrefs:
        seen.setdefault(f"{base}{href}", None)
    return list(seen)


class MetroStatusConfig(BaseModel):
    """thessmetro.gr server-renders live status with no JSON counterpart."""

    url: str = "https://www.thessmetro.gr/"


@register
class MetroStatusPlugin(SourcePlugin):
    """Live Thessaloniki Metro line and station status.

    Only elevator state is read. The station colour attribute
    (``data-bs-station``) was observed reporting ``ektos`` for four stations
    while the line itself read "Normal Operation" and their elevators were
    healthy — its semantics are undocumented and self-contradictory, so it is
    not interpreted. ``data-bs-elevator-issue`` carries an explicit,
    self-describing message and is trustworthy.
    """

    kind = "metro_status"
    config_model = MetroStatusConfig

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = MetroStatusConfig.model_validate(config)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=_UA) as client:
            try:
                resp = await client.get(cfg.url)
                resp.raise_for_status()
                html = resp.text
            except httpx.HTTPError as exc:
                logger.warning("metro_status.fetch_failed err=%s", exc)
                return

        for station, issue in _elevator_issues(html):
            text = f"Μετρό Θεσσαλονίκης — σταθμός {station}: πρόβλημα ανελκυστήρα. {issue}"
            yield PluginArtifact(
                uri=f"metro_status://elevator/{station}",
                data=text.encode("utf-8"),
                mime="text/plain",
                meta={"station": station, "kind": "elevator"},
            )

        operation = _line_operation(html)
        # Normal operation is the steady state, not news. Only a departure
        # from it is a problem worth extracting.
        if operation and not _is_normal(operation):
            text = f"Μετρό Θεσσαλονίκης — κατάσταση γραμμής: {operation}"
            yield PluginArtifact(
                uri="metro_status://line",
                data=text.encode("utf-8"),
                mime="text/plain",
                meta={"kind": "line_status", "status": operation},
            )


def _elevator_issues(html: str) -> list[tuple[str, str]]:
    """(station, issue) for every station reporting an elevator problem.

    Matched tag-agnostically: the attributes live on a ``<div>``, not the
    ``<li>`` an earlier version assumed, and the markup is regenerated often
    enough that pinning the element name buys nothing but breakage.

    ``data-bs-elevator-issue`` is empty string when the lifts are fine, so an
    empty result here is the normal, healthy case — not a parse failure.
    """
    issues: list[tuple[str, str]] = []
    for block in re.findall(r"(?is)<[a-z]+\b[^>]*data-bs-stationname=[^>]*>", html):
        name = _attr(block, "data-bs-stationname")
        issue = _attr(block, "data-bs-elevator-issue")
        if name and issue.strip():
            issues.append((name, strip_html(issue, limit=300)))
    return issues


def _line_operation(html: str) -> str:
    match = re.search(
        r'(?is)<div[^>]*class="[^"]*eventbox-header-operation-name[^"]*"[^>]*>(.*?)</div>',
        html,
    )
    return strip_html(match.group(1), limit=200) if match else ""


def _attr(tag: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', tag, re.IGNORECASE)
    return match.group(1) if match else ""


def _is_normal(operation: str) -> bool:
    lowered = operation.lower()
    return "normal" in lowered or "κανονικ" in lowered
