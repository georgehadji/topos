# ruff: noqa: RUF001
"""LLM-backed Greek sentiment classification.

Greek is the technical risk here, not the plumbing. General-purpose sentiment
tooling is trained overwhelmingly on English and degrades on Greek without
saying so, which is why this goes through the same LLM stack the extractor
uses rather than a bolt-on library, and why the golden fixtures matter more
than the model choice.

The prompt is code (AGENTS.md): versioned, and the version is stored with
every label so a reclassification can be told apart from a model change.

Fails loudly. If the model returns anything but the three permitted labels,
or the wrong number of them, the batch is rejected rather than defaulted to
neutral — a fabricated neutral would be indistinguishable from a measured one,
which is the defect class the ΔΕΔΔΗΕ sample fallback belonged to.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from topos.domain.sentiment import SentimentLabel

logger = logging.getLogger(__name__)

__all__ = ["PROMPT_VER", "OpenRouterSentiment"]

PROMPT_VER = "sentiment-el-1.0.0"

_PROMPT = """Είσαι ταξινομητής συναισθήματος για ελληνικά δημοσιεύματα και \
δημόσια έγγραφα που αφορούν προβλήματα μιας εκλογικής περιφέρειας.

Για κάθε κείμενο, απάντησε με ΕΝΑ από τα: negative, neutral, positive.

Κανόνες:
- negative: το κείμενο περιγράφει βλάβη, καθυστέρηση, παράπονο, αποτυχία ή \
δυσαρέσκεια πολιτών.
- neutral: διοικητική ή ενημερωτική ανακοίνωση χωρίς αξιολόγηση.
- positive: το κείμενο περιγράφει επίλυση, βελτίωση ή ολοκλήρωση έργου.
- Ταξινόμησε τον ΤΟΝΟ του κειμένου, όχι το πόσο σοβαρό είναι το θέμα.

Επίστρεψε ΜΟΝΟ έγκυρο JSON, χωρίς επεξήγηση:
{{"labels": ["negative", "neutral", ...]}}

Τα κείμενα, με τη σειρά:
{texts}"""

_MAX_CHARS = 1200


class OpenRouterSentiment:
    """Satisfies ``service.ports.SentimentAnalyzer`` structurally."""

    def __init__(self, llm_client: Any, model: str) -> None:
        self._llm = llm_client
        self._model = model

    async def __call__(self, texts: list[str]) -> list[SentimentLabel]:
        if not texts:
            return []

        numbered = "\n".join(f"{i + 1}. {t[:_MAX_CHARS]}" for i, t in enumerate(texts))
        result = await self._llm.complete(
            prompt=_PROMPT.format(texts=numbered),
            model=self._model,
            response_format={"type": "json_object"},
        )

        labels = _parse(result, expected=len(texts))
        if labels is None:
            raise ValueError("sentiment: model returned no usable label list")
        return labels


def _parse(result: Any, *, expected: int) -> list[SentimentLabel] | None:
    """Labels from the model reply, or None when unusable.

    Length must match: a short list would silently misalign labels with texts,
    attributing one document's tone to another.
    """
    raw = _text_of(result)
    if not raw:
        return None

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None

    items = payload.get("labels") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) != expected:
        logger.warning(
            "sentiment.length_mismatch expected=%d got=%s",
            expected,
            len(items) if isinstance(items, list) else "n/a",
        )
        return None

    labels: list[SentimentLabel] = []
    for item in items:
        try:
            labels.append(SentimentLabel(str(item).strip().lower()))
        except ValueError:
            logger.warning("sentiment.unknown_label value=%r", item)
            return None
    return labels


def _text_of(result: Any) -> str:
    """The provider stack returns either a string or a chat-completion dict."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        choices = result.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                return str(message.get("content", ""))
        return str(result.get("output_text", ""))
    return ""
