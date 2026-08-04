"""Greek behaviour regression, frozen against real ingested strings.

AGENTS.md: "Greek is the dominant technical risk. Never assume English-grade
accuracy. Golden fixtures required for Greek behaviour."

Approval testing. A failure here means behaviour changed — decide whether the
change is an improvement and update ``greek_cases.json`` deliberately, or
revert. Never edit an expectation to make a red test green.

Cases marked ``known_gap`` are inputs that *should* resolve and do not. They
are asserted to still fail, so fixing one is a visible, intentional diff
rather than something that silently drifts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from topos.adapters.authority import resolve_authority
from topos.adapters.geocode import geocode
from topos.domain.relevance import is_out_of_area

pytestmark = pytest.mark.golden

_CASES: dict[str, Any] = json.loads(
    (Path(__file__).parent / "greek_cases.json").read_text(encoding="utf-8")
)

_PLACES = 4  # coordinate rounding, decimal places
# Recall floor for toponyms that are expected to resolve. Raise this when the
# gazetteer improves; never lower it to make a run pass.
_MIN_GEOCODE_RECALL = 1.0


def _ids(cases: list[dict[str, Any]]) -> list[str]:
    return [c["input"][:40] or "<empty>" for c in cases]


# ── Geocoding ───────────────────────────────────────────────────────────────

_GEO = _CASES["geocode"]
_GEO_RESOLVES = [c for c in _GEO if not c.get("known_gap") and c.get("expected", "?") is not None]
_GEO_NULL = [c for c in _GEO if c.get("expected", "?") is None and not c.get("known_gap")]
_GEO_GAPS = [c for c in _GEO if c.get("known_gap")]


@pytest.mark.parametrize("case", _GEO_RESOLVES, ids=_ids(_GEO_RESOLVES))
def test_toponym_resolves_to_frozen_coordinates(case: dict[str, Any]) -> None:
    result = geocode(case["input"])
    assert result is not None, f"regression: {case['input']!r} no longer resolves"
    assert round(result.geom.lat, _PLACES) == case["lat"]
    assert round(result.geom.lon, _PLACES) == case["lon"]
    assert str(result.granularity) == case["granularity"]


@pytest.mark.parametrize("case", _GEO_NULL, ids=_ids(_GEO_NULL))
def test_text_naming_no_place_stays_unresolved(case: dict[str, Any]) -> None:
    """Inventing a centroid for placeless text is the failure that matters:
    it puts a pin on a map for a problem that has no location."""
    assert geocode(case["input"]) is None


@pytest.mark.parametrize("case", _GEO_GAPS, ids=_ids(_GEO_GAPS))
def test_known_gaps_still_unresolved(case: dict[str, Any]) -> None:
    """Fails when a gap is fixed — that is the point. Move the case up into
    the resolving set with its real coordinates."""
    assert geocode(case["input"]) is None, (
        f"{case['input']!r} now resolves — move it out of known_gap"
    )


def test_geocode_recall_does_not_regress() -> None:
    hits = sum(1 for c in _GEO_RESOLVES if geocode(c["input"]) is not None)
    recall = hits / len(_GEO_RESOLVES)
    assert recall >= _MIN_GEOCODE_RECALL, f"recall {recall:.2f} < floor {_MIN_GEOCODE_RECALL}"


# ── Out-of-area filtering ───────────────────────────────────────────────────

_RELEVANCE = _CASES["relevance"]


@pytest.mark.parametrize("case", _RELEVANCE, ids=_ids(_RELEVANCE))
def test_out_of_area_classification(case: dict[str, Any]) -> None:
    assert is_out_of_area(case["input"]) is case["out_of_area"]


# ── Authority resolution ────────────────────────────────────────────────────

_AUTHORITY = _CASES["authority"]


@pytest.mark.parametrize("case", _AUTHORITY, ids=_ids(_AUTHORITY))
def test_authority_resolution(case: dict[str, Any]) -> None:
    result = resolve_authority(case["input"])
    if case["authority"] is None:
        assert result is None
    else:
        assert result is not None, f"{case['input']!r} resolved to nothing"
        assert result.name == case["authority"]
