"""Entity resolution: blocking + feature functions.

Pure domain logic. No IO, no imports from topos.* packages.

Slice 2.2. Two-phase ER:
  1. Blocking: cheap predicate to select candidate pairs (block using
     category + location proximity + text overlap).
  2. Feature functions: compute a similarity score vector for each pair.
     The vector feeds the classifier in slice 2.3.

Every function here is deterministic — tested with literal inputs/outputs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MentionPair:
    """A pair of mention/claim records being compared for ER."""

    id_a: str
    id_b: str
    predicate_a: str
    predicate_b: str
    text_a: str
    text_b: str
    lat_a: float | None
    lon_a: float | None
    lat_b: float | None
    lon_b: float | None


@dataclass(frozen=True, slots=True)
class FeatureVector:
    """Feature vector for a mention pair. All values 0.0-1.0."""

    same_predicate: float  # 1.0 if predicates match
    text_similarity: float  # token overlap ratio (0.0-1.0)
    geo_proximity: float  # inverse distance ratio (0.0-1.0, 1.0 = same point)
    combined: float  # weighted product of the above


# ── Blocking ─────────────────────────────────────────────────────────────────


def same_block(pair: MentionPair) -> bool:
    """Cheap predicate: should this pair be considered for ER?

    A pair passes the block if they share the same predicate OR
    their text has significant token overlap (>= 50%).
    """
    if pair.predicate_a == pair.predicate_b:
        return True
    overlap = _token_overlap_ratio(pair.text_a, pair.text_b)
    return overlap >= 0.50  # noqa: PLR2004


# ── Feature functions ────────────────────────────────────────────────────────


def compute_features(pair: MentionPair) -> FeatureVector:
    """Compute the feature vector for a mention pair.

    All features are normalised to [0.0, 1.0].
    """
    same_pred = 1.0 if pair.predicate_a == pair.predicate_b else 0.0
    text_sim = _token_overlap_ratio(pair.text_a, pair.text_b)
    geo_prox = _geo_proximity(pair.lat_a, pair.lon_a, pair.lat_b, pair.lon_b)
    combined = (same_pred * 0.4 + text_sim * 0.35 + geo_prox * 0.25)

    return FeatureVector(
        same_predicate=same_pred,
        text_similarity=text_sim,
        geo_proximity=geo_prox,
        combined=round(combined, 4),
    )


# ── Helper functions ─────────────────────────────────────────────────────────


def _token_overlap_ratio(text_a: str, text_b: str) -> float:
    """Compute the Jaccard-like token overlap between two texts."""
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)  # type: ignore[no-any-return]


def _geo_proximity(
    lat_a: float | None, lon_a: float | None,
    lat_b: float | None, lon_b: float | None,
) -> float:
    """Compute geographic proximity as inverse normalized distance.

    Returns 1.0 if both points are None (unknown location).
    Returns 0.0 if one has location but the other doesn't.
    Uses a simple Euclidean approximation at Thessaloniki's latitude
    (1 degree ≈ 111km). Distances > 5km return 0.
    """
    if lat_a is None and lon_a is None and lat_b is None and lon_b is None:
        return 1.0
    if lat_a is None or lon_a is None or lat_b is None or lon_b is None:
        return 0.0

    # Approximate: 1 degree lat ≈ 111km, 1 degree lon ≈ 111*cos(40.6°) ≈ 84km
    dlat = (lat_a - lat_b) * 111.0
    dlon = (lon_a - lon_b) * 84.0
    dist_km = (dlat ** 2 + dlon ** 2) ** 0.5

    # Normalize: 0km → 1.0, 5km → 0.0
    return max(0.0, 1.0 - dist_km / 5.0)


def er_decision(
    features: FeatureVector,
    threshold: float = 0.55,
) -> tuple[str, float]:
    """Make an ER decision from a feature vector.

    Returns (verdict, score) where verdict is "match", "non-match", or
    "uncertain". Callers with uncertain pairs push them to the review queue.

    This is a simple linear classifier. Phase 2.3 upgrades to a learned
    classifier trained on labelled pairs.
    """
    if features.combined >= threshold:
        return "match", features.combined
    elif features.combined >= threshold - 0.15:
        return "uncertain", features.combined
    else:
        return "non-match", features.combined
