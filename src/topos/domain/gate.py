"""Should this document's text be sent to the LLM at all? (Phase 6 #6.2, #6.3)

`is_out_of_area` and `simhash`/`hamming` already exist and cost nothing, but
until now nothing consulted them before paying for extraction — only after,
in `persist_extraction`. Of 19 problems ingested so far, 5 were out-of-area:
roughly a quarter of extraction spend bought rows that were discarded.

Specification pattern: refusal carries a *reason*, not a bare bool. A
silently skipped document is indistinguishable from one that legitimately
extracted nothing, and this project has already been bitten by exactly that
ambiguity (see ADR-014 — an unmeasured cost that looked like a free one).

The existing post-extraction `is_out_of_area` filter in `service/mentions.py`
stays. This gate is the optimisation; that filter is the correctness
boundary, and belt-and-braces costs nothing at that layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from topos.domain.relevance import is_out_of_area
from topos.domain.simhash import hamming, simhash

__all__ = ["ExtractionDecision", "should_extract"]

# Hamming distance, out of 64 bits, below which two documents count as the
# same wire copy rather than two independent ones. Conservative: a handful
# of reworded sentences still matches; two genuinely different articles on
# the same event do not.
_NEAR_DUP_MAX_HAMMING = 3


@dataclass(frozen=True, slots=True)
class ExtractionDecision:
    extract: bool
    reason: str | None = None  # populated only when extract is False


def should_extract(text: str, *, recent_hashes: tuple[int, ...] = ()) -> ExtractionDecision:
    """Pure gate. `recent_hashes` are simhash fingerprints of documents
    already extracted, fetched by the caller — this function does no IO.

    A near-duplicate document contributes no new claims: ARCHITECTURE.md's
    scoring section already treats "three outlets republishing one wire" as
    one source for `reach`, so skipping it is consistent with how a
    duplicate is meant to count, not a shortcut around it.
    """
    if is_out_of_area(text):
        return ExtractionDecision(False, "out_of_area")

    fingerprint = simhash(text)
    for other in recent_hashes:
        if hamming(fingerprint, other) <= _NEAR_DUP_MAX_HAMMING:
            return ExtractionDecision(False, "near_duplicate")

    return ExtractionDecision(True)
