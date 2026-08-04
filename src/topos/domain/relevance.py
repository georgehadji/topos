# ruff: noqa: RUF001, RUF003
"""Is an extracted claim about this constituency at all?

Nothing upstream checks. Geography enters the pipeline only as *query bias* —
Greek search strings naming Θεσσαλονίκη, a domain allowlist — and none of it
constrains what actually comes back. A national wire story about wildfires in
Attica satisfies every one of those and lands in the dataset as a
constituency problem.

The check here is deliberately **negative**: it drops a claim that names a
region outside the constituency, rather than requiring one that names a region
inside it. A positive test would be far more aggressive and wrong — most
genuine findings (a school-maintenance delay in council minutes, a void
tender) name no place at all, because the document's whole context is already
the municipality. Requiring a toponym would delete them.

Deterministic and pure, per ARCHITECTURE.md: "Geocoding, deduplication,
scoring, routing and alerting are deterministic code — do not put an LLM in
them." A denylist is auditable and testable; an LLM relevance judge is neither.
"""

from __future__ import annotations

import re

__all__ = ["is_out_of_area"]

# Places outside Α΄ Θεσσαλονίκης that Greek national coverage routinely names.
# Both scripts: extraction returns Greek and Latin spellings interchangeably.
#
# Deliberately absent: "Μακεδονία"/"Macedonia" (Thessaloniki is *in* Macedonia)
# and "Ελλάδα"/"Greece". A term only belongs here if its presence genuinely
# argues the document is about somewhere else.
_OUT_OF_AREA: frozenset[str] = frozenset(
    {
        # Attica and the capital
        "αττικη",
        "attica",
        "αθηνα",
        "athens",
        "πειραιας",
        "piraeus",
        # Other mainland regions and cities
        "πατρα",
        "patras",
        "αχαια",
        "λαρισα",
        "larisa",
        "larissa",
        "βολος",
        "volos",
        "μαγνησια",
        "ιωαννινα",
        "ioannina",
        "ηπειρος",
        "epirus",
        "θεσσαλια",
        "thessaly",
        "πελοποννησος",
        "peloponnese",
        "στερεα ελλαδα",
        "καλαματα",
        "kalamata",
        "σπαρτη",
        "τριπολη",
        "λαμια",
        "χαλκιδα",
        # Macedonia/Thrace prefectures that are not Thessaloniki
        "χαλκιδικη",
        "halkidiki",
        "chalkidiki",
        "καβαλα",
        "kavala",
        "σερρες",
        "serres",
        "κιλκις",
        "kilkis",
        "πελλα",
        "pella",
        "ημαθια",
        "imathia",
        "βεροια",
        "veroia",
        "ναουσα",
        "εδεσσα",
        "πιερια",
        "pieria",
        "κατερινη",
        "katerini",
        "κοζανη",
        "kozani",
        "καστορια",
        "φλωρινα",
        "γρεβενα",
        "δραμα",
        "drama",
        "ξανθη",
        "xanthi",
        "κομοτηνη",
        "komotini",
        "εβρος",
        "evros",
        "αλεξανδρουπολη",
        "alexandroupoli",
        "θρακη",
        "thrace",
        # Islands
        "θασος",
        "thasos",
        "κρητη",
        "crete",
        "ηρακλειο",
        "heraklion",
        "χανια",
        "chania",
        "ροδος",
        "rhodes",
        "κερκυρα",
        "corfu",
        "μυκονος",
        "mykonos",
        "σαντορινη",
        "santorini",
        "λεσβος",
        "lesvos",
        "χιος",
        "chios",
        "σαμος",
        "samos",
        "ζακυνθος",
        "κεφαλονια",
        "αιγαιο",
        "aegean",
        "κυκλαδες",
        "cyclades",
        "δωδεκανησα",
        "ιονιο",
        "σποραδες",
        "ευβοια",
    }
)

# Constituency terms. Their presence vetoes the drop: a document comparing
# Thessaloniki with Athens is still about Thessaloniki.
_HOME: frozenset[str] = frozenset(
    {
        "θεσσαλονικη",
        "θεσσαλονικης",
        "thessaloniki",
        "thessalonikis",
        "salonica",
        "salonika",
        "καλαμαρια",
        "kalamaria",
        "τουμπα",
        "toumba",
        "χαριλαου",
        "charilaou",
        "harilaou",
        "τσιμισκη",
        "tsimiski",
        "εγνατια",
        "egnatia",
        "σταυρουπολη",
        "stavroupoli",
        "νεαπολη",
        "neapoli",
        "συκιες",
        "sykies",
        "πυλαια",
        "pylaia",
        "πανοραμα",
        "panorama",
        "θερμη",
        "thermi",
        "ωραιοκαστρο",
        "oraiokastro",
        "αμπελοκηποι",
        "ampelokipoi",
        "πολιχνη",
        "polichni",
        "ευκαρπια",
        "efkarpia",
        "χορτιατης",
        "chortiatis",
        "λαγκαδας",
        "lagkadas",
        "μενεμενη",
        "ελευθεριο",
        "κορδελιο",
        "πευκα",
        "ρετζικι",
        "τριανδρια",
        "triandria",
        "αριστοτελους",
        "aristotelous",
    }
)

_ACCENT_MAP = str.maketrans("άέήίόύώϊϋΐΰ", "αεηιουωιυιυ")


def _fold(text: str) -> str:
    """Lowercase and strip accents — same normalisation as adapters.geocode."""
    return text.lower().translate(_ACCENT_MAP)


# Greek inflects place names, and the denylist stores nominatives: a feed
# saying "Π.Ε. ΠΕΛΛΑΣ" must match the entry "πελλα". Allowing up to two
# trailing Greek letters before the word boundary covers the common genitive
# and accusative endings (-ς, -ν, -ας) without swallowing unrelated words —
# "δράμα" still does not match "δραματική", which needs four.
_INFLECTION = r"[α-ω]{0,2}"


def _pattern(terms: frozenset[str]) -> re.Pattern[str]:
    # Longest first so "ανω τουμπα" wins over "τουμπα"; word-bounded so a short
    # term never matches inside an unrelated word.
    ordered = sorted(terms, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in ordered) + r")" + _INFLECTION + r"\b")


_OUT_RE = _pattern(_OUT_OF_AREA)
_HOME_RE = _pattern(_HOME)


def is_out_of_area(text: str) -> bool:
    """True when *text* is about somewhere else, and not also about here.

    Returns False for text naming no place at all — silence is not evidence of
    being elsewhere, and most council-minute findings carry no toponym.
    """
    if not text:
        return False
    folded = _fold(text)
    if _HOME_RE.search(folded):
        return False
    return _OUT_RE.search(folded) is not None
