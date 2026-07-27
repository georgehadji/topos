"""Extraction service: uses LlmClient to extract claims from chunks.

Slice 1.6. Calls the LLM with a structured-output prompt, validates
the response against the extraction schema, and yields ExtractedChunks.
"""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from decimal import Decimal
from typing import Any

from topos.domain.extraction import (
    ClaimAtom,
    ExtractedChunk,
    ExtractedClaim,
    Extraction,
    Span,
)
from topos.domain.types import ArtifactId

logger = logging.getLogger(__name__)

# Greek text uses Unicode characters that ruff flags as ambiguous.
# This is intentional — "A' Thessalonikis" is a proper name.
_PROMPT_TEMPLATE = (
    "You are a policy analyst for the constituency of A' Thessalonikis.\n"
    "Your task is to read the following excerpt from a Greek public-sector"
    " document and extract ANY mention of a citizen-affecting problem.\n"
    "\n"
    'A "problem" is something that negatively affects residents of the'
    " constituency:\n"
    "  - Infrastructure issues (roads, water, electricity, public transport)\n"
    "  - Health and safety hazards\n"
    "  - Environmental problems (pollution, waste, green space)\n"
    "  - Administrative issues (delays, missing services, bureaucratic"
    " failures)\n"
    "  - Social issues (housing, education, access to services)\n"
    "\n"
    "Rules (ARCHITECTURE.md L1/L2):\n"
    "  - DO NOT extract any natural person's name, ethnicity, religion,"
    " political opinion, health condition, or union membership.\n"
    "  - DO NOT speculate or infer. Only extract what is explicitly stated.\n"
    '  - An "authority" is an office or organization, never a person.\n'
    "\n"
    "For each problem mention, extract:\n"
    '  1. **predicate** \u2014 a short text key like "road_damage",'
    ' "water_leak", "air_pollution"\n'
    "  2. **value** \u2014 a JSON value describing the problem"
    " (string, number, or object)\n"
    "  3. **span_start** \u2014 the character offset where evidence"
    " for this claim begins\n"
    "  4. **span_end** \u2014 the character offset where evidence ends\n"
    "\n"
    "If there are NO citizen-affecting problems in this text, return an"
    " empty JSON array.\n"
    "\n"
    "Respond ONLY with a JSON array. No explanation, no markdown,"
    " no preamble.\n"
    "\n"
    "Document excerpt:\n"
    "---\n"
    "{chunk_text}\n"
    "---"
)


async def extract_chunk(
    llm_client: Any,
    ord: int,
    text: str,
    *,
    model: str = "mistralai/mistral-large-2512",
) -> ExtractedChunk:
    """Extract claims from a single chunk using the LLM."""
    prompt = _PROMPT_TEMPLATE.format(chunk_text=text)

    try:
        result = await llm_client.complete(
            prompt=prompt,
            model=model,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.exception("LLM extraction failed for chunk %d: %s", ord, exc)
        return ExtractedChunk(ord=ord, text=text, claims=[])

    raw = _parse_response(result)
    claims = _validate_claims(raw, text)
    return ExtractedChunk(ord=ord, text=text, claims=claims)


def _parse_response(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the JSON array from the LLM response."""
    try:
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return []
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("claims", "problems", "results", "data"):
                val = parsed.get(key)
                if isinstance(val, list):
                    return val
        return []
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return []


def _validate_claims(raw: list[Any], chunk_text: str) -> list[ExtractedClaim]:
    """Validate raw LLM output into ExtractedClaim objects.

    Rejects claims with unresolvable spans (L5).
    """
    result: list[ExtractedClaim] = []
    text_len = len(chunk_text)

    for item in raw:
        if not isinstance(item, dict):
            continue
        predicate = item.get("predicate", "")
        value = item.get("value", "")
        span_start = item.get("span_start", item.get("start"))
        span_end = item.get("span_end", item.get("end"))

        if not predicate or not value:
            continue

        if not isinstance(span_start, int) or not isinstance(span_end, int):
            continue
        if span_start < 0 or span_end > text_len or span_start >= span_end:
            continue

        confidence: Decimal | None = None
        raw_conf = item.get("confidence")
        if raw_conf is not None:
            with suppress(ValueError, TypeError):
                confidence = Decimal(str(raw_conf))

        result.append(
            ExtractedClaim(
                claim=ClaimAtom(
                    predicate=predicate,
                    value=value,
                    confidence=confidence,
                ),
                span=Span(start=span_start, end=span_end),
            )
        )

    return result


async def extract_artifact(
    llm_client: Any,
    artifact_id: ArtifactId,
    chunks: list[tuple[int, str]],
    *,
    model: str = "mistralai/mistral-large-2512",
) -> Extraction:
    """Extract claims across all chunks of an artifact."""
    extracted_chunks: list[ExtractedChunk] = []

    for ord, text in chunks:
        chunk_result = await extract_chunk(
            llm_client=llm_client,
            ord=ord,
            text=text,
            model=model,
        )
        extracted_chunks.append(chunk_result)

    return Extraction(
        artifact_id=str(artifact_id),
        chunks=extracted_chunks,
        prompt_ver="1.0.0",
    )
