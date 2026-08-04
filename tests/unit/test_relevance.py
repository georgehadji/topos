# ruff: noqa: RUF001
"""Unit tests: out-of-area claim detection.

Pure domain, literal inputs. The "real junk" cases below are verbatim from
claims that reached a generated newsletter on 2026-08-04 — a Thessaloniki
digest carrying Attica wildfires and Thasos ferry traffic.
"""

from __future__ import annotations

import pytest

from topos.domain.relevance import is_out_of_area


@pytest.mark.parametrize(
    "text",
    [
        "Η πυρκαγιά στη Δυτική Αττική επεκτείνεται σε περιοχές",
        "Intense mobility due to ferry departures to Thasos and the northeastern Aegean",
        "φωτιές στην Αττική, 700.000 στρέμματα έγιναν στάχτη",
        "Major flooding reported in Crete",
        "Road closure in Larissa",
    ],
)
def test_real_junk_that_reached_a_newsletter_is_dropped(text: str) -> None:
    assert is_out_of_area(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "διακοπή νερού στη Σταυρούπολη",
        "Thessaloniki Metro Line 1 out of service",
        "κατασκευές στην κοινότητα Πεύκων",
        "Scheduled power outage in areas of Kalochori",
    ],
)
def test_genuine_local_findings_are_kept(text: str) -> None:
    assert is_out_of_area(text) is False


def test_placeless_council_business_is_kept() -> None:
    """Most real findings name no place — the document's context is already the
    municipality. A positive 'must name Thessaloniki' test would delete these."""
    text = (
        "Tender for the procurement of personal protective equipment for municipal "
        "employees declared void for certain items"
    )
    assert is_out_of_area(text) is False


def test_comparison_mentioning_both_places_is_kept() -> None:
    """Naming Athens does not make a Thessaloniki story an Athens story."""
    text = "Το μετρό Θεσσαλονίκης σε σύγκριση με το μετρό της Αθήνας"
    assert is_out_of_area(text) is False


def test_latin_home_spelling_also_vetoes_the_drop() -> None:
    assert is_out_of_area("Comparing Thessaloniki and Athens transport") is False


def test_empty_text_is_not_out_of_area() -> None:
    assert is_out_of_area("") is False


def test_accents_do_not_defeat_the_match() -> None:
    assert is_out_of_area("πυρκαγιά στην Αττική") is True
    assert is_out_of_area("πυρκαγια στην Αττικη") is True


def test_macedonia_is_not_treated_as_elsewhere() -> None:
    """Thessaloniki is in Macedonia — listing it would drop local findings."""
    assert is_out_of_area("Κεντρική Μακεδονία, έργα υποδομής") is False


def test_substring_of_a_longer_word_does_not_match() -> None:
    """Word-bounded: 'δραματικη' must not trigger on the city 'Δράμα'."""
    assert is_out_of_area("η κατασταση ειναι δραματικη") is False
