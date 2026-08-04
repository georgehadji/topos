"""Natural-hazard sources: severe weather warnings and seismicity.

Unlike the civic feeds these return *records*, not prose, so each plugin
renders one short Greek/English document per event for the extractor to read.
The rendering is mechanical string formatting over fields that came off the
wire — no field is invented, and an event with a missing field simply omits
that line (ADR-012: never a stand-in for data we do not have).

Both endpoints are anonymous and bbox/region-filterable, so the constituency
filter happens server-side rather than by downloading Greece and discarding.

Air quality is deliberately absent. EEA's endpoint that responds without auth
(``/City``) returns a *city list*, not measurements; real readings need a
multi-step Parquet download, and OpenAQ v3 requires a key. Neither is a feed,
and both yield time series rather than problem statements — a different shape
of work than this pipeline does.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel

from topos.adapters.sources.base import PluginArtifact, SourcePlugin
from topos.adapters.sources.registry import register

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Topos/0.1"}

# Central Macedonia in Meteoalarm's EMMA region coding.
_EMMA_CENTRAL_MACEDONIA = "GR007"


class MeteoalarmConfig(BaseModel):
    """Meteoalarm republishes ΕΜΥ's CAP warnings; ΕΜΥ's own XML paths are gone."""

    feed_url: str = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-greece"
    emma_id: str = _EMMA_CENTRAL_MACEDONIA
    max_items: int = 20


@register
class MeteoalarmPlugin(SourcePlugin):
    """Severe-weather warnings for Central Macedonia."""

    kind = "meteoalarm"
    config_model = MeteoalarmConfig

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = MeteoalarmConfig.model_validate(config)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=_UA) as client:
            try:
                resp = await client.get(cfg.feed_url)
                resp.raise_for_status()
                payload = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("meteoalarm.fetch_failed err=%s", exc)
                return

        for warning in _meteoalarm_warnings(payload)[: cfg.max_items]:
            # The feed wraps each entry as {"alert": {...}}; older CAP dumps
            # put the same fields at the top level.
            nested = warning.get("alert")
            alert: dict[str, Any] = nested if isinstance(nested, dict) else warning
            info = _pick_info(alert.get("info"))
            if not info:
                continue
            if cfg.emma_id and not _covers_region(info.get("area") or [], cfg.emma_id):
                continue

            text = _render_warning(info)
            if not text:
                continue
            yield PluginArtifact(
                uri=f"meteoalarm://{alert.get('identifier') or info.get('event') or 'warning'}",
                data=text.encode("utf-8"),
                mime="text/plain",
                meta={"event": info.get("event"), "severity": info.get("severity")},
            )


def _meteoalarm_warnings(payload: Any) -> list[dict[str, Any]]:
    """The feed nests alerts under `warnings`; tolerate a bare list too."""
    if isinstance(payload, dict):
        items = payload.get("warnings") or payload.get("alerts") or []
    else:
        items = payload
    return [w for w in items if isinstance(w, dict)] if isinstance(items, list) else []


def _pick_info(info: Any) -> dict[str, Any]:
    """CAP repeats `info` once per language. Prefer Greek, else English, else first.

    A dict (single-language feed) passes through unchanged.
    """
    if isinstance(info, dict):
        return info
    if not isinstance(info, list):
        return {}
    blocks = [b for b in info if isinstance(b, dict)]
    if not blocks:
        return {}
    for prefix in ("el", "en"):
        for block in blocks:
            if str(block.get("language", "")).lower().startswith(prefix):
                return block
    return blocks[0]


def _covers_region(areas: Any, emma_id: str) -> bool:
    """True when any area geocode carries the wanted EMMA_ID."""
    area_list = areas if isinstance(areas, list) else [areas]
    for area in area_list:
        if not isinstance(area, dict):
            continue
        geocodes = area.get("geocode") or []
        geocode_list = geocodes if isinstance(geocodes, list) else [geocodes]
        for code in geocode_list:
            if isinstance(code, dict) and str(code.get("value", "")).upper() == emma_id.upper():
                return True
    return False


def _render_warning(info: dict[str, Any]) -> str:
    """One warning as a short document. Absent fields are omitted, not faked."""
    lines = []
    for label, key in (
        ("Πρόειδοποίηση", "event"),
        ("Σοβαρότητα", "severity"),
        ("Από", "onset"),
        ("Έως", "expires"),
        ("Περιγραφή", "description"),
        ("Οδηγίες", "instruction"),
    ):
        value = info.get(key)
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


# Felt-report threshold. Below roughly M3 an event is instrumental only — real
# for seismologists, not a civic problem, and the local network detects to M0.7,
# so an unfiltered feed is thousands of rows of noise.
_DEFAULT_MIN_MAGNITUDE = 3.0


class EarthquakeConfig(BaseModel):
    """NOA's FDSN service. EMSC (``seismicportal.eu``) speaks the same protocol
    and can be swapped in via ``base_url``; NOA is the default because the
    Greek national network resolves far smaller local events."""

    base_url: str = "https://eida.gein.noa.gr/fdsnws/event/1/query"
    min_latitude: float = 40.0
    max_latitude: float = 41.2
    min_longitude: float = 22.0
    max_longitude: float = 23.8
    min_magnitude: float = _DEFAULT_MIN_MAGNITUDE
    lookback_days: int = 7
    max_items: int = 20


@register
class EarthquakePlugin(SourcePlugin):
    """Seismicity in the Thessaloniki bounding box."""

    kind = "earthquakes"
    config_model = EarthquakeConfig

    async def fetch(self, config: BaseModel) -> AsyncIterator[PluginArtifact]:
        cfg = EarthquakeConfig.model_validate(config)
        # starttime is not optional here: without it NOA's Apache rejects the
        # whole query with a bare 400 before FDSN ever sees it. This is also
        # what makes lookback_days mean anything — it was parsed and ignored.
        start = datetime.now(UTC) - timedelta(days=cfg.lookback_days)
        params: dict[str, str] = {
            "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "minlatitude": str(cfg.min_latitude),
            "maxlatitude": str(cfg.max_latitude),
            "minlongitude": str(cfg.min_longitude),
            "maxlongitude": str(cfg.max_longitude),
            "minmagnitude": str(cfg.min_magnitude),
            "format": "text",
        }

        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=_UA) as client:
            try:
                resp = await client.get(cfg.base_url, params=params)
                resp.raise_for_status()
                body = resp.text
            except httpx.HTTPError as exc:
                logger.warning("earthquakes.fetch_failed err=%s", exc)
                return

        for event in _parse_fdsn_text(body)[: cfg.max_items]:
            text = (
                f"Σεισμός μεγέθους {event['magnitude']} {event['mag_type']}. "
                f"Τοποθεσία: {event['place']}. "
                f"Χρόνος: {event['time']}. "
                f"Βάθος: {event['depth']} km. "
                f"Συντεταγμένες: {event['lat']}, {event['lon']}."
            )
            yield PluginArtifact(
                uri=f"earthquakes://{event['event_id']}",
                data=text.encode("utf-8"),
                mime="text/plain",
                meta={
                    "magnitude": event["magnitude"],
                    "lat": event["lat"],
                    "lon": event["lon"],
                },
            )


_FDSN_COLUMNS = 13


def _parse_fdsn_text(body: str) -> list[dict[str, str]]:
    """Parse FDSN `format=text`: pipe-delimited, one `#`-prefixed header line.

    Columns: EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|
    Contributor|ContributorID|MagType|Magnitude|MagAuthor|EventLocationName
    """
    events: list[dict[str, str]] = []
    for line in body.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < _FDSN_COLUMNS:
            continue
        events.append(
            {
                "event_id": parts[0],
                "time": parts[1],
                "lat": parts[2],
                "lon": parts[3],
                "depth": parts[4],
                "mag_type": parts[9],
                "magnitude": parts[10],
                "place": parts[12],
            }
        )
    return events


__all__ = ["EarthquakePlugin", "MeteoalarmPlugin"]
