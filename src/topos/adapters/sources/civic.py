"""Civic announcement feeds: municipalities, region, utilities, operators.

Every URL here was probed on 2026-08-04 and returned real content. Sources
that *look* available but are verifiably empty are recorded in the module
docstring below rather than given a plugin — a registered plugin that can
never yield anything is worse than none, because `topos-cli sources` then
advertises coverage the system does not have.

Verified dead, deliberately absent:

* **ΟΑΣΘ** ``oasth.gr`` — WordPress with zero posts (``X-WP-Total: 0``); the
  RSS is valid and permanently empty. ΟΑΣΘ is no longer the transit
  authority; ΟΣΕΘ is (see ``oseth.py``).
* **ΟΣΕΘ RSS** ``oseth.com.gr/rss.xml`` — 100 KB containing exactly one item,
  a FAQ page from 2024. Misconfigured Drupal view. The announcements index is
  scraped instead.
* **ΕΥΑΘ water outages** — ``eyath.gr/feed/`` serves corporate PR (dividends,
  hiring). The ``vlaves-ydreysis`` category is the right one but its newest
  post is 2019-08-01. Water cuts reach us only secondhand via news.
* **"Βελτιώνω την πόλη μου"** — the ImproveMyCity instance the CKAN metadata
  still advertises returns empty rows, and every ``com_imc`` route 500s.
"""

from __future__ import annotations

from topos.adapters.sources.feedbase import FeedConfig, FeedPlugin
from topos.adapters.sources.registry import register


class ThessalonikiWpConfig(FeedConfig):
    # The REST endpoint behind thessaloniki.gr. The existing `municipality`
    # plugin regex-scrapes the same site's RSS for PDF links; this returns the
    # post bodies as JSON, which needs no scraping and carries real dates.
    feeds: list[str] = ["https://www.thessaloniki.gr/wp-json/wp/v2/posts?per_page=25"]
    max_per_feed: int = 25


@register
class ThessalonikiWpPlugin(FeedPlugin):
    """Δήμος Θεσσαλονίκης announcements via WordPress REST."""

    kind = "thessaloniki_wp"
    config_model = ThessalonikiWpConfig


class PkmConfig(FeedConfig):
    feeds: list[str] = ["https://www.pkm.gov.gr/feed/"]
    max_per_feed: int = 20


@register
class PkmPlugin(FeedPlugin):
    """Περιφέρεια Κεντρικής Μακεδονίας — regional works and permits."""

    kind = "pkm"
    config_model = PkmConfig


class SuburbsConfig(FeedConfig):
    """The Α΄ Θεσσαλονίκης municipalities outside the city proper.

    Δήμος Νεάπολης-Συκεών is absent: the site is not WordPress and exposes no
    feed. Κορδελιό-Εύοσμος is absent too — its feed responds but the newest
    item is from March 2025.
    """

    feeds: list[str] = [
        # No www: the certificate on www.kalamaria.gr is issued for a
        # different hostname, so TLS verification fails there. The bare
        # domain serves the same feed with a valid certificate.
        "https://kalamaria.gr/feed/",
        "https://thermi.gov.gr/feed/",
        "https://pavlosmelas.gr/feed/",
        "https://ampelokipi-menemeni.gr/feed/",
        "https://pilea-hortiatis.gr/feed/",
        "https://dimosdelta.gr/feed/",
        "https://oraiokastro.gr/feed/",
    ]
    max_per_feed: int = 8


@register
class SuburbsPlugin(FeedPlugin):
    """Suburban municipalities of the constituency."""

    kind = "suburbs"
    config_model = SuburbsConfig


class WasteConfig(FeedConfig):
    feeds: list[str] = ["https://fodsakm.gr/feed/"]
    max_per_feed: int = 10


@register
class WastePlugin(FeedPlugin):
    """ΦοΔΣΑ Κεντρικής Μακεδονίας — waste management authority."""

    kind = "waste"
    config_model = WasteConfig


class PortConfig(FeedConfig):
    feeds: list[str] = ["https://www.thpa.gr/feed/"]
    max_per_feed: int = 10


@register
class PortPlugin(FeedPlugin):
    """ΟΛΘ — Thessaloniki Port Authority."""

    kind = "port"
    config_model = PortConfig


class MetroNewsConfig(FeedConfig):
    """Category 11 is ``ανακοινώσεις`` on thessmetro.gr.

    Low volume by nature: all 12 posts on the site span 2025-01 to 2026-05,
    about 0.6/month. This is a press-release channel, not an alerting one —
    same-day disruptions never appear here. For those see ``metro_status.py``.
    """

    feeds: list[str] = ["https://www.thessmetro.gr/wp-json/wp/v2/posts?categories=11&per_page=20"]
    max_per_feed: int = 20


@register
class MetroNewsPlugin(FeedPlugin):
    """Μετρό Θεσσαλονίκης (THEMA S.A.) announcements."""

    kind = "metro_news"
    config_model = MetroNewsConfig
