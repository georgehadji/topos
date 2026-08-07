# ruff: noqa: E501
"""Pipeline handlers: concrete implementations for each FSM state.

Slices 1.5 - 1.9. Decoupled and modular handlers that process artifacts,
textify them, extract claims using the LLM client, geocode locations,
and project claims to event-sourced mentions.
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from typing import Any

import asyncpg

from topos.domain.gate import should_extract
from topos.domain.simhash import simhash
from topos.domain.types import PipelineRow, PipelineState
from topos.service.er import run_er
from topos.service.extraction import extract_artifact
from topos.service.mentions import persist_extraction
from topos.service.ports import AuthorityResolver, BlobReader, Geocoder, TextExtractor
from topos.service.scoring import score_all

logger = logging.getLogger(__name__)

# document.text_method, by what the bytes turned out to be.
_TEXT_METHOD = {
    "application/pdf": "pdf_text",
    "text/html": "html",
    "application/json": "json",
}


# Keys that usually hold a place, tried before anything else in the claim.
_PLACE_KEYS = (
    "location",
    "street",
    "address",
    "neighbourhood",
    "area",
    "affected_areas",
    "municipality",
    "region",
)


def _toponym_candidates(value: Any) -> list[str]:
    """Strings from a claim value worth trying against the geocoder.

    Place-like keys first, then every other string (the geocoder scans free
    text, so a description can still yield a hit).
    """
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, dict):
        return []

    preferred: list[str] = []
    rest: list[str] = []
    for key, raw in value.items():
        for item in raw if isinstance(raw, list) else [raw]:
            if not isinstance(item, str) or not item.strip():
                continue
            (preferred if key in _PLACE_KEYS else rest).append(item)
    return preferred + rest


class PipelineHandlers:
    """Production pipeline handlers linked to each FSM state."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        llm_client: Any,
        geocoder: Geocoder,
        blob: BlobReader,
        extract_text: TextExtractor,
        *,
        model: str,
        authority_resolver: AuthorityResolver | None = None,
    ) -> None:
        self.pool = pool
        self.llm_client = llm_client
        self.geocoder = geocoder
        self.blob = blob
        self.extract_text = extract_text
        # Optional: authority resolution shares handle_extracted's claim scan
        # but is a separate, smaller alias table (adapters/authority) — a
        # missing resolver degrades to "no authority linked", same tolerance
        # as a missing geocoder result.
        self.authority_resolver = authority_resolver
        # The one place this string lives. Passed through to extract_artifact
        # and into the extraction_run row it writes, so provenance always
        # names the model that was actually configured to run — never a
        # literal that drifts from it.
        self.model = model

    async def handle_fetched(self, row: PipelineRow) -> None:
        """FETCHED -> TEXTIFIED.

        Reads raw artifact, decodes it as UTF-8 native text, and writes to document table.
        """
        async with self.pool.acquire() as conn:
            # Check if document already exists
            exists = await conn.fetchval(
                "SELECT 1 FROM document WHERE artifact_id = $1::uuid",
                row.artifact_id,
            )
            if exists:
                return

            # Read artifact details
            artifact = await conn.fetchrow(
                "SELECT uri, mime, blob_key FROM artifact WHERE id = $1::uuid",
                row.artifact_id,
            )
            if not artifact:
                return

            blob_key = artifact["blob_key"]
            if not blob_key:
                raise ValueError(f"artifact {row.artifact_id} has no blob_key; nothing to textify")

            # The bytes we actually fetched — never a stand-in for them (ADR-012).
            data = await self.blob.get(blob_key)
            mime = artifact["mime"] or ""
            text = self.extract_text(data, mime)

            if not text:
                # A scan, an empty body, or an unreadable format. Park it for the
                # OCR slice rather than inventing content.
                raise ValueError(
                    f"no_text_layer: cannot extract text from {artifact['uri']} ({mime})"
                )

            method = _TEXT_METHOD.get(mime.split(";", 1)[0].strip().lower(), "native")

            await conn.execute(
                """
                INSERT INTO document (artifact_id, lang, text, text_method)
                VALUES ($1::uuid, 'el', $2, $3)
                ON CONFLICT (artifact_id) DO NOTHING
                """,
                row.artifact_id,
                text,
                method,
            )

    async def handle_textified(self, row: PipelineRow) -> None:
        """TEXTIFIED -> CHUNKED.

        Splits document text into chunks and writes to chunk table.
        """
        async with self.pool.acquire() as conn:
            # Check if chunk already exists
            exists = await conn.fetchval(
                "SELECT 1 FROM chunk WHERE artifact_id = $1::uuid AND ord = 0",
                row.artifact_id,
            )
            if exists:
                return

            # Read document text
            text = await conn.fetchval(
                "SELECT text FROM document WHERE artifact_id = $1::uuid",
                row.artifact_id,
            )
            if not text:
                return

            # Slice into 1 single chunk for native-text sources
            await conn.execute(
                """
                INSERT INTO chunk (artifact_id, ord, span, text)
                VALUES ($1::uuid, 0, int4range(0, $2), $3)
                ON CONFLICT (artifact_id, ord) DO NOTHING
                """,
                row.artifact_id,
                len(text),
                text,
            )

    async def handle_chunked(self, row: PipelineRow) -> None:
        """CHUNKED -> EXTRACTED.

        Gates on relevance and near-duplication (Phase 6 #6.2/#6.3) before
        paying for extraction, then invokes the LLM and persists claims.
        A gate refusal still advances the state — a skipped document and one
        that legitimately yielded nothing look the same to the FSM; only the
        log line tells them apart (domain/gate.py).
        """
        async with self.pool.acquire() as conn:
            chunks_rows = await conn.fetch(
                "SELECT ord, text FROM chunk WHERE artifact_id = $1::uuid ORDER BY ord",
                row.artifact_id,
            )
            if not chunks_rows:
                return

            chunks = [(r["ord"], r["text"]) for r in chunks_rows]
            full_text = "\n".join(text for _, text in chunks)

            # ponytail: linear scan of recent extracted chunks — one simhash
            # comparison per row, fine at the ~10^2 documents/day this
            # pipeline sees. Upgrade to a BK-tree or an indexed hash bucket
            # if volume reaches 10^6.
            recent_rows = await conn.fetch(
                """
                SELECT c.text FROM chunk c
                JOIN extraction_run er ON er.artifact_id = c.artifact_id
                WHERE c.artifact_id <> $1::uuid
                ORDER BY er.started_at DESC
                LIMIT 200
                """,
                row.artifact_id,
            )
            recent_hashes = tuple(simhash(r["text"]) for r in recent_rows)

            decision = should_extract(full_text, recent_hashes=recent_hashes)
            if not decision.extract:
                logger.info(
                    "extraction_skipped artifact=%s reason=%s",
                    row.artifact_id,
                    decision.reason,
                )
                return

            # Run LLM extraction
            extraction = await extract_artifact(
                self.llm_client,
                row.artifact_id,
                chunks,
                model=self.model,
            )

            # Persist claims using the Mentions service
            # Create extraction run metadata row
            run_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO extraction_run (id, artifact_id, prompt_ver, model, params, started_at, ok)
                VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, now(), true)
                """,
                run_id,
                row.artifact_id,
                extraction.prompt_ver,
                self.model,
                "{}",
            )

            # Persist claims to DB
            await persist_extraction(self.pool, extraction, run_id=run_id)

    async def handle_extracted(self, row: PipelineRow) -> None:
        """EXTRACTED -> GEOCODED.

        Performs geocoding and authority-resolution lookups for all
        extracted claims. Both scan the same candidate strings — extraction
        never emits a structured place or authority field, only free text —
        so one pass over the claim covers them.
        """
        async with self.pool.acquire() as conn:
            # Read all claims for this artifact
            claims = await conn.fetch(
                "SELECT id, value, predicate FROM claim WHERE artifact_id = $1::uuid",
                row.artifact_id,
            )

            for claim in claims:
                val = claim["value"]
                if isinstance(val, str):
                    with contextlib.suppress(Exception):
                        val = json.loads(val)

                candidates = _toponym_candidates(val)

                # Try every string in the claim, place-like keys first. Models
                # put the location wherever they like — affected_areas,
                # neighbourhood, or buried in description — so whitelisting
                # three key names geocoded almost nothing.
                geo_res = None
                for candidate in candidates:
                    geo_res = self.geocoder(candidate)
                    if geo_res:
                        break

                authority_res = None
                if self.authority_resolver is not None:
                    for candidate in candidates:
                        authority_res = self.authority_resolver(candidate)
                        if authority_res:
                            break

                if geo_res is None and authority_res is None:
                    continue

                prob_ids = await conn.fetch(
                    "SELECT problem_id FROM problem_claim WHERE claim_id = $1::uuid",
                    claim["id"],
                )
                for p_row in prob_ids:
                    if geo_res:
                        await conn.execute(
                            """
                            UPDATE problem SET
                              geom = ST_SetSRID(ST_MakePoint($1, $2), 4326),
                              geo_conf = $3
                            WHERE id = $4::uuid
                            """,
                            geo_res.geom.lon,
                            geo_res.geom.lat,
                            geo_res.confidence,
                            p_row["problem_id"],
                        )
                    if authority_res:
                        await conn.execute(
                            "UPDATE problem SET authority_id = $1::uuid WHERE id = $2::uuid",
                            authority_res.id,
                            p_row["problem_id"],
                        )

    async def handle_geocoded(self, _row: PipelineRow) -> None:
        """GEOCODED -> RESOLVED.

        Runs entity resolution over every candidate problem, then scores.
        Neither is scoped to this row's artifact — ER compares across the
        whole candidate set, and scoring's `reach` counts sources per problem,
        so both are corpus-wide by nature. Idempotent (see run_er's
        docstring): re-running after every artifact is wasteful at scale but
        harmless, and correct is cheaper to reason about than
        scoped-but-subtly-wrong. The blocking-key ceiling that will matter
        first is noted in service/er.py.

        Order matters: scoring must follow ER. A problem that ER is about to
        fold into another would otherwise be scored on its own partial
        evidence, and the surviving problem would be scored before inheriting
        the loser's claims — understating reach on the row that survives.
        """
        await run_er(self.pool)
        await score_all(self.pool)

    def get_map(self) -> dict[PipelineState, Any]:
        """Get the full FSM State to Handler mapping."""
        return {
            PipelineState.FETCHED: self.handle_fetched,
            PipelineState.TEXTIFIED: self.handle_textified,
            PipelineState.CHUNKED: self.handle_chunked,
            PipelineState.EXTRACTED: self.handle_extracted,
            PipelineState.GEOCODED: self.handle_geocoded,
        }
