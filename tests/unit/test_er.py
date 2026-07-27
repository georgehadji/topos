"""Unit tests: entity resolution blocking and feature functions.

Pure domain tests — literal inputs, literal expected outputs, no mocks.
"""

from __future__ import annotations

from topos.domain.er import (
    FeatureVector,
    MentionPair,
    compute_features,
    er_decision,
    same_block,
)

_A = "00000000-0000-0000-0000-000000000001"
_B = "00000000-0000-0000-0000-000000000002"


def test_same_block_shared_predicate() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="road_damage",
        text_a="pothole on Egnatia",
        text_b="pot hole eg nat ia",
        lat_a=None,
        lon_a=None,
        lat_b=None,
        lon_b=None,
    )
    assert same_block(pair) is True


def test_same_block_high_text_overlap() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="water_leak",
        text_a="large pothole on Egnatia street",
        text_b="pothole on Egnatia street is large",
        lat_a=None,
        lon_a=None,
        lat_b=None,
        lon_b=None,
    )
    # "pothole on Egnatia street large" = 5/6 ≈ 0.83 >= 0.50
    assert same_block(pair) is True


def test_same_block_low_overlap() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="water_leak",
        text_a="broken pavement",
        text_b="water pipe burst at square",
        lat_a=None,
        lon_a=None,
        lat_b=None,
        lon_b=None,
    )
    assert same_block(pair) is False


def test_features_same_predicate_same_text() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="road_damage",
        text_a="pothole on Egnatia",
        text_b="pothole on Egnatia",
        lat_a=40.64,
        lon_a=22.94,
        lat_b=40.64,
        lon_b=22.94,
    )
    fv = compute_features(pair)
    assert fv.same_predicate == 1.0
    assert fv.text_similarity == 1.0
    assert fv.geo_proximity == 1.0
    assert fv.combined == 1.0


def test_features_different_predicates() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="water_leak",
        text_a="pothole",
        text_b="pipe burst",
        lat_a=40.64,
        lon_a=22.94,
        lat_b=40.65,
        lon_b=22.95,
    )
    fv = compute_features(pair)
    assert fv.same_predicate == 0.0
    assert fv.text_similarity == 0.0
    # ~1.5km apart → proximity ≈ 1 - 1.5/5 = 0.7
    assert 0.60 < fv.geo_proximity < 0.80
    assert 0.10 < fv.combined < 0.30


def test_features_both_no_location() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="noise",
        predicate_b="noise",
        text_a="loud music at night",
        text_b="loud music at night",
        lat_a=None,
        lon_a=None,
        lat_b=None,
        lon_b=None,
    )
    fv = compute_features(pair)
    assert fv.geo_proximity == 1.0  # both unknown = 1.0
    assert fv.same_predicate == 1.0
    assert fv.text_similarity == 1.0


def test_features_one_location_missing() -> None:
    pair = MentionPair(
        id_a=_A,
        id_b=_B,
        predicate_a="road_damage",
        predicate_b="road_damage",
        text_a="pothole",
        text_b="pothole",
        lat_a=40.64,
        lon_a=22.94,
        lat_b=None,
        lon_b=None,
    )
    fv = compute_features(pair)
    assert fv.geo_proximity == 0.0


def test_er_decision_clear_match() -> None:

    fv = FeatureVector(same_predicate=1.0, text_similarity=1.0, geo_proximity=1.0, combined=1.0)
    verdict, _score = er_decision(fv)
    assert verdict == "match"
    assert _score >= 0.55


def test_er_decision_clear_non_match() -> None:

    fv = FeatureVector(same_predicate=0.0, text_similarity=0.0, geo_proximity=0.0, combined=0.0)
    verdict, _score = er_decision(fv)
    assert verdict == "non-match"


def test_er_decision_uncertain() -> None:

    # combined score in the uncertain band: 0.40-0.55
    fv = FeatureVector(same_predicate=1.0, text_similarity=0.3, geo_proximity=0.0, combined=0.50)
    verdict, _score = er_decision(fv, threshold=0.55)
    assert verdict == "uncertain"
