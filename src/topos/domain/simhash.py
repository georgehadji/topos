"""64-bit simhash fingerprint for near-duplicate text detection (Phase 6 #6.3).

A locality-sensitive fingerprint: near-identical texts (a wire story copied
by three outlets) produce fingerprints a small Hamming distance apart, so
"is this a near-duplicate of something already seen" becomes an integer
comparison instead of a second LLM call. Pure and deterministic, per
ARCHITECTURE.md: "deduplication ... [is] deterministic code — do not put an
LLM in [it]."
"""

from __future__ import annotations

import hashlib
import re

__all__ = ["hamming", "simhash"]

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_BITS = 64


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _hash_token(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=_BITS // 8).digest()
    return int.from_bytes(digest, "big")


def simhash(text: str) -> int:
    """A 64-bit fingerprint over word shingles.

    Empty or single-word text collapses toward 0 and is not a meaningful
    fingerprint — callers must not feed it text too short to carry signal.
    """
    weights = [0] * _BITS
    for token in _tokens(text):
        h = _hash_token(token)
        for bit in range(_BITS):
            weights[bit] += 1 if (h >> bit) & 1 else -1

    fingerprint = 0
    for bit in range(_BITS):
        if weights[bit] > 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming(a: int, b: int) -> int:
    """Number of differing bits between two fingerprints."""
    return (a ^ b).bit_count()
