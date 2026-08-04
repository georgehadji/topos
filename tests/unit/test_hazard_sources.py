# ruff: noqa: RUF001
"""Unit tests: hazard and transport source parsing.

Fixtures are trimmed copies of real responses captured 2026-08-04.
"""

from __future__ import annotations

from topos.adapters.sources.hazards import (
    _covers_region,
    _meteoalarm_warnings,
    _parse_fdsn_text,
    _pick_info,
    _render_warning,
)
from topos.adapters.sources.transport import (
    _article_links,
    _elevator_issues,
    _is_normal,
    _line_operation,
    _main_content,
)

# ── Meteoalarm ──────────────────────────────────────────────────────────────

_WARNING = {
    "alert": {
        "identifier": "2.49.0.0.300.0.GR.260730111700.000010002",
        "info": [
            {
                "language": "en-GB",
                "event": "Moderate high-temperature warning",
                "severity": "Moderate",
                "description": "High air temperature values",
                "area": [{"geocode": [{"value": "GR007", "valueName": "EMMA_ID"}]}],
            },
            {
                "language": "el-GR",
                "event": "Υψηλές θερμοκρασίες",
                "description": "Υψηλές τιμές θερμοκρασίας",
                "area": [{"geocode": [{"value": "GR007", "valueName": "EMMA_ID"}]}],
            },
        ],
    }
}


def test_warnings_are_read_from_the_warnings_key() -> None:
    assert _meteoalarm_warnings({"warnings": [_WARNING]}) == [_WARNING]


def test_pick_info_prefers_greek_over_english() -> None:
    """CAP repeats `info` once per language; the Greek block is the useful one."""
    info = _pick_info(_WARNING["alert"]["info"])
    assert info["event"] == "Υψηλές θερμοκρασίες"


def test_pick_info_falls_back_to_english_when_no_greek() -> None:
    blocks = [{"language": "en-GB", "event": "Rain"}]
    assert _pick_info(blocks)["event"] == "Rain"


def test_pick_info_accepts_a_bare_dict() -> None:
    assert _pick_info({"event": "X"})["event"] == "X"


def test_pick_info_of_nothing_is_empty() -> None:
    assert _pick_info(None) == {}
    assert _pick_info([]) == {}


def test_region_filter_matches_the_emma_id() -> None:
    areas = [{"geocode": [{"value": "GR007", "valueName": "EMMA_ID"}]}]
    assert _covers_region(areas, "GR007") is True
    assert _covers_region(areas, "GR002") is False


def test_region_filter_rejects_a_warning_for_another_region() -> None:
    """West Sterea warnings must not become Thessaloniki problems."""
    areas = [{"areaDesc": "West Sterea", "geocode": [{"value": "GR002"}]}]
    assert _covers_region(areas, "GR007") is False


def test_render_warning_omits_absent_fields_rather_than_inventing_them() -> None:
    text = _render_warning({"event": "Καύσωνας", "severity": "Moderate"})
    assert "Καύσωνας" in text
    assert "Οδηγίες" not in text
    assert "None" not in text


# ── Earthquakes (FDSN text) ─────────────────────────────────────────────────

_FDSN = (
    "#EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|"
    "ContributorID|MagType|Magnitude|MagAuthor|EventLocationName|EventType\n"
    "noa2026pcsvy|2026-08-03T21:43:47.3|40.612335|22.920685|12.4|NOA|noa|||"
    "ML|3.4|NOA|THESSALONIKI|earthquake\n"
)


def test_fdsn_text_parses_the_columns_by_position() -> None:
    events = _parse_fdsn_text(_FDSN)
    assert len(events) == 1
    event = events[0]
    assert event["event_id"] == "noa2026pcsvy"
    assert event["lat"] == "40.612335"
    assert event["lon"] == "22.920685"
    assert event["magnitude"] == "3.4"
    assert event["place"] == "THESSALONIKI"


def test_fdsn_tolerates_the_extra_eventtype_column() -> None:
    """NOA returns 14 columns; the documented schema has 13."""
    assert _parse_fdsn_text(_FDSN)[0]["mag_type"] == "ML"


def test_fdsn_skips_the_header_and_blank_lines() -> None:
    assert _parse_fdsn_text("#EventID|Time\n\n") == []


def test_fdsn_skips_short_malformed_rows() -> None:
    assert _parse_fdsn_text("a|b|c\n") == []


# ── Metro status ────────────────────────────────────────────────────────────

_STATION_OK = (
    '<div data-bs-stationname="Νέος Σιδηροδρομικός Σταθμός" data-bs-station="ektos" '
    'data-bs-elevator="Οι ανελκυστήρες λειτουργούν κανονικά" data-bs-elevator-issue=""></div>'
)
_STATION_BAD = (
    '<div data-bs-stationname="Fleming" data-bs-station="kanoniki" '
    'data-bs-elevator="Εκτός" data-bs-elevator-issue="Ανελκυστήρας εκτός λειτουργίας"></div>'
)


def test_healthy_station_reports_no_issue() -> None:
    """Empty data-bs-elevator-issue is the normal case, not a parse failure."""
    assert _elevator_issues(_STATION_OK) == []


def test_station_with_an_elevator_issue_is_reported() -> None:
    assert _elevator_issues(_STATION_BAD) == [("Fleming", "Ανελκυστήρας εκτός λειτουργίας")]


def test_elevator_issues_are_found_on_a_div_not_only_an_li() -> None:
    """The attributes live on a <div>; assuming <li> silently found nothing."""
    assert len(_elevator_issues(_STATION_OK + _STATION_BAD)) == 1


def test_contradictory_station_colour_is_ignored() -> None:
    """data-bs-station reads 'ektos' on a station whose lifts are fine — its
    semantics are undocumented, so only the elevator fields are trusted."""
    assert _elevator_issues(_STATION_OK) == []


def test_line_operation_is_extracted() -> None:
    html = '<div class="eventbox-header-operation-name">Κανονική Λειτουργία</div>'
    assert _line_operation(html) == "Κανονική Λειτουργία"


def test_normal_operation_recognised_in_both_languages() -> None:
    assert _is_normal("Normal Operation") is True
    assert _is_normal("Κανονική Λειτουργία") is True
    assert _is_normal("Διακοπή δρομολογίων") is False


# ── ΟΣΕΘ index ──────────────────────────────────────────────────────────────


def test_article_links_exclude_navigation() -> None:
    """The index carries ~45 nav links; only /el/article/ entries are content."""
    html = (
        '<a href="/el/anazitisi-dromologion-leoforeion">nav</a>'
        '<a href="/el/tropopoiiseis-diktyoy">nav</a>'
        '<a href="/el/article/o-oseth-stin-episimi-paroysiasi">real</a>'
    )
    assert _article_links(html, base="https://oseth.com.gr") == [
        "https://oseth.com.gr/el/article/o-oseth-stin-episimi-paroysiasi"
    ]


def test_article_links_deduplicate() -> None:
    html = '<a href="/el/article/x">1</a><a href="/el/article/x">2</a>'
    assert len(_article_links(html, base="https://x.gr")) == 1


def test_main_content_prefers_the_article_element() -> None:
    """Whole-page stripping put the nav menu at the front of every artifact."""
    html = "<nav>Main navigation Αναζήτηση</nav><article>Το κείμενο</article><footer>f</footer>"
    assert _main_content(html) == "<article>Το κείμενο</article>"


def test_main_content_falls_back_to_the_whole_page() -> None:
    html = "<div>no article element</div>"
    assert _main_content(html) == html
