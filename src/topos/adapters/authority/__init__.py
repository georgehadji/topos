"""Authority resolution: alias table -> known Greek public bodies.

Same shape as adapters.geocode (ARCHITECTURE.md: "Geocoding, deduplication,
scoring, routing and alerting are deterministic code — do not put an LLM in
them"). Claims name authorities as free text inside claim.value —
extraction.py's prompt tells the model what an authority *is* (an office,
never a person — constraint L1) but never asks for one as a structured
field, so this resolves the same way the geocoder resolves an unstructured
place name: scan known aliases in whatever string the claim happens to hold.

The ids below MUST match alembic/versions/007_authority_seed.py — this
module resolves a name to one of those rows' primary keys but never queries
the database itself. Add an authority in both places, or not at all.
"""

from __future__ import annotations

import re

from topos.domain.authority import AuthorityRef
from topos.domain.types import AuthorityLevel

_EYATH = "27c9d268-35b6-5462-873f-93cb7894a51a"
_DEDDIE = "0873a2dc-5dad-5350-85d5-09722a430de4"
_OASTH = "bab806fa-1686-538b-98e2-03dd2075b95e"
_DEI = "dc6a6090-f08e-5695-945f-15803738efdd"
_DIMOS_THESSALONIKIS = "83eda05c-7c5b-52ec-80ed-e44c71a87d9f"

_AUTHORITIES: dict[str, AuthorityRef] = {
    "eyath": AuthorityRef(id=_EYATH, name="ΕΥΑΘ", level=AuthorityLevel.UTILITY, confidence=0.90),
    "deddie": AuthorityRef(
        id=_DEDDIE, name="ΔΕΔΔΗΕ", level=AuthorityLevel.UTILITY, confidence=0.90
    ),
    "oasth": AuthorityRef(id=_OASTH, name="ΟΑΣΘ", level=AuthorityLevel.UTILITY, confidence=0.90),
    "dei": AuthorityRef(id=_DEI, name="ΔΕΗ", level=AuthorityLevel.UTILITY, confidence=0.90),
    "dimos thessalonikis": AuthorityRef(
        id=_DIMOS_THESSALONIKIS,
        name="Δήμος Θεσσαλονίκης",
        level=AuthorityLevel.MUNICIPALITY,
        confidence=0.90,
    ),
}

# Every scannable spelling -> canonical key in _AUTHORITIES. Greek, Latin, and
# the exact English gloss extraction has actually returned
# ("ΕΥΑΘ (Water Supply and Sewerage Company)") all map to the same row.
_ALIASES: dict[str, str] = {
    "ευαθ": "eyath",
    "eyath": "eyath",
    "water supply and sewerage company": "eyath",
    "δεδδηε": "deddie",
    "deddhe": "deddie",  # matches the deddhe source plugin's kind spelling
    "deddie": "deddie",
    "οασθ": "oasth",
    "oasth": "oasth",
    "δεη": "dei",
    "dei": "dei",
    "δημος θεσσαλονικης": "dimos thessalonikis",
    "δημου θεσσαλονικης": "dimos thessalonikis",  # genitive: "...του Δήμου Θεσσαλονίκης"
    "municipality of thessaloniki": "dimos thessalonikis",
    "thessaloniki municipality": "dimos thessalonikis",
}

_ACCENT_MAP = str.maketrans("άέήίόύώ", "αεηιουω")


def _fold(text: str) -> str:
    return text.strip().lower().translate(_ACCENT_MAP)


_SCANNABLE: dict[str, str] = {_fold(k): v for k, v in _ALIASES.items()}

# Longest alias first, word-bounded — same reasoning as adapters.geocode's
# _SCAN_RE: a short alias like "dei" must not match inside an unrelated word.
_SCAN_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in sorted(_SCANNABLE, key=len, reverse=True)) + r")\b"
)


def resolve_authority(text: str) -> AuthorityRef | None:
    """Find the most specific known authority mentioned inside *text*.

    Returns None if no known authority appears — never guesses at a
    responsible office from context alone (that would be exactly the kind of
    blame-attribution constraint L7 warns against; L7 is documented in
    docs/INITIAL_PROMPT.v2.md, not yet carried into ARCHITECTURE.md's table).
    """
    folded = _fold(text)
    if not folded:
        return None

    match = _SCAN_RE.search(folded)
    if match is None:
        return None

    return _AUTHORITIES[_SCANNABLE[match.group(1)]]
