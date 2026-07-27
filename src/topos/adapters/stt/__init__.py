"""Speech-to-text pipeline for municipal council recordings.

Phase 3.5. Uses the configured LLM provider's audio transcription
endpoint (OpenRouter supports Whisper via several providers).

The STT adapter produces raw Greek text which flows into the standard
pipeline (chunk → extract → mention).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from topos.config import get_settings


class SttAdapter:
    """Speech-to-text adapter using the configured LLM provider."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.llm_api_key
        self._base_url = settings.llm_base_url.rstrip("/")

    async def transcribe(
        self,
        audio_data: bytes,
        *,
        filename: str = "recording.mp3",
        model: str = "openai/whisper-large-v3",
        language: str = "el",
    ) -> str:
        """Transcribe audio to Greek text using Whisper via OpenRouter."""
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                },
                files={
                    "file": (filename, audio_data, "audio/mpeg"),
                    "model": (None, model),
                    "language": (None, language),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("text", ""))

    async def transcribe_file(self, path: str | Path) -> str:
        """Transcribe an audio file from disk."""
        data = Path(path).read_bytes()
        return await self.transcribe(data, filename=Path(path).name)


async def ingest_audio(
    pool: Any,
    audio_data: bytes,
    *,
    source: str = "council_recording",
    uri: str = "",
    stt: SttAdapter | None = None,
) -> dict[str, Any]:
    """Ingest an audio recording through the pipeline.

    1. Transcribe audio to text via Whisper
    2. Create a text artifact (text/plain)
    3. Push into the pipeline for extraction
    """
    stt = stt or SttAdapter()
    text = await stt.transcribe(audio_data)

    import hashlib
    import uuid

    aid = uuid.uuid4()
    sha256 = hashlib.sha256(audio_data).digest()
    text_data = text.encode("utf-8")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO artifact
              (id, source_id, uri, sha256, blob_key, mime, bytes, fetched_at)
            VALUES ($1::uuid, $2, $3, $4::bytea, $5, $6, $7, now())
            """,
            aid,
            source,
            uri or f"stt://{aid}",
            sha256,
            str(aid),
            "text/plain",
            len(text_data),
        )

        await conn.execute(
            """
            INSERT INTO document (artifact_id, lang, text, text_method)
            VALUES ($1::uuid, 'el', $2, 'whisper-large-v3')
            """,
            aid,
            text,
        )

        # Chunk the text and add to pipeline
        chunks = _chunk_text(text, max_chars=2000)
        for i, (start, end, chunk_text) in enumerate(chunks):
            await conn.execute(
                """
                INSERT INTO chunk (id, artifact_id, ord, span, text)
                VALUES (nextval('chunk_id_seq'), $1::uuid, $2, int4range($3, $4), $5)
                """,
                aid,
                i,
                start,
                end,
                chunk_text,
            )

        await conn.execute(
            """
            INSERT INTO pipeline (artifact_id, state)
            VALUES ($1::uuid, 'fetched'::pipe_state)
            """,
            aid,
        )

    return {
        "artifact_id": str(aid),
        "text_length": len(text),
        "chunks": len(chunks),
    }


def _chunk_text(text: str, max_chars: int = 2000) -> list[tuple[int, int, str]]:
    """Split text into chunks at sentence boundaries."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[tuple[int, int, str]] = []
    current = ""
    start = 0

    for sentence in sentences:
        if len(current) + len(sentence) > max_chars and current:
            end = start + len(current)
            chunks.append((start, end, current.strip()))
            start = end
            current = sentence
        else:
            current += " " + sentence if current else sentence

    if current.strip():
        end = start + len(current)
        chunks.append((start, end, current.strip()))

    return chunks
