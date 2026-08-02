# ruff: noqa: RUF003
"""``topos-cli gazetteer`` — regenerate the geocoding seed from OpenStreetMap.

Coordinates are fetched, never hand-written: a lat/lon typed from memory is
unverifiable, and this pipeline exists to keep evidence traceable.

Source is the public Overpass API — no key, but it is a shared free service, so
this is a deliberate manual step rather than something the worker calls.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import typer

from topos.adapters.geocode.seed import SCHEMA_VERSION, SEED_PATH
from topos.interfaces.cli.io import emit, fail

cli = typer.Typer(help="Manage the geocoding gazetteer.", no_args_is_help=True)

# Α΄ Θεσσαλονίκης and its surroundings. Wider than the constituency on purpose:
# claims routinely name neighbouring municipalities.
_BBOX = "40.45,22.65,40.90,23.25"

_PLACE_KINDS = "city|town|village|suburb|neighbourhood|quarter|hamlet|borough"
# Named through-roads only. Every residential street would be tens of thousands
# of ways, most of them ambiguous by name alone.
_ROAD_KINDS = "motorway|trunk|primary|secondary|tertiary"

_QUERY = f"""
[out:json][timeout:180];
(
  node["place"~"^({_PLACE_KINDS})$"]["name"]({_BBOX});
  way["highway"~"^({_ROAD_KINDS})$"]["name"]({_BBOX});
);
out center tags;
"""

_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

_SETTLEMENTS = {"city", "town", "village", "municipality"}


@cli.command()
def refresh(
    output: str = typer.Option("", help="Write here instead of the packaged seed."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Fetch places and major roads from OpenStreetMap into the gazetteer seed."""
    try:
        elements = _fetch()
    except Exception as exc:
        fail(f"overpass fetch failed: {type(exc).__name__}: {exc}", json_out=json_out)

    entries = _to_entries(elements)
    if not entries:
        fail("overpass returned no usable elements", json_out=json_out)

    path = Path(output) if output else SEED_PATH
    payload = {
        "schema": SCHEMA_VERSION,
        "source": "OpenStreetMap via Overpass API (ODbL)",
        "bbox": _BBOX,
        "fetched_at": datetime.now(UTC).isoformat(),
        "entries": entries,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    kinds: dict[str, int] = {}
    for e in entries:
        kinds[e["granularity"]] = kinds.get(e["granularity"], 0) + 1
    emit({"written": str(path), "entries": len(entries), "by_granularity": kinds}, as_json=json_out)


def _fetch() -> list[dict[str, Any]]:
    """Query Overpass, trying mirrors in turn — the main host rate-limits."""
    last: Exception | None = None
    for endpoint in _ENDPOINTS:
        try:
            resp = httpx.post(
                endpoint,
                data={"data": _QUERY},
                timeout=httpx.Timeout(240.0, connect=15.0),
                headers={"User-Agent": "Topos/0.1 (constituency intelligence)"},
            )
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            if elements:
                return list(elements)
            last = RuntimeError(f"{endpoint} returned no elements")
        except Exception as exc:
            last = exc
    raise last or RuntimeError("no Overpass endpoint responded")


def _to_entries(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten Overpass elements into seed entries, most specific first."""
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    for el in elements:
        tags = el.get("tags") or {}
        label = (tags.get("name") or "").strip()
        if not label:
            continue

        if el.get("type") == "node":
            lat, lon = el.get("lat"), el.get("lon")
            place = (tags.get("place") or "").lower()
            granularity = "municipality" if place in _SETTLEMENTS else "neighbourhood"
        else:
            center = el.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
            granularity = "street"

        if lat is None or lon is None:
            continue

        # OSM often carries a Latin form; extraction returns those constantly
        # ("Thessaloniki Metro", "Kalochori"). Taking it from the data beats
        # transliterating by hand.
        names = [label, tags.get("name:en", ""), tags.get("int_name", "")]
        for raw_name in names:
            name = (raw_name or "").strip().lower()
            if not name:
                continue
            key = f"{name}|{granularity}"
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                {
                    "name": name,
                    "label": label,
                    "lat": round(float(lat), 6),
                    "lon": round(float(lon), 6),
                    "granularity": granularity,
                }
            )

    # Settlements before neighbourhoods before streets: load_seed keeps the
    # first entry for a given name, and a town is the safer default reading.
    order = {"municipality": 0, "neighbourhood": 1, "street": 2}
    entries.sort(key=lambda e: (order[e["granularity"]], e["name"]))
    return entries
