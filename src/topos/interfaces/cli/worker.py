# ruff: noqa: ARG002, E501
"""Worker entrypoint: `python -m topos.interfaces.cli.worker`.

Drives the main pipeline claim loop with concurrent-safe SKIP LOCKED claims.
See ARCHITECTURE.md > The pipeline.
"""

from __future__ import annotations

import asyncio
import re
import signal
from contextlib import suppress

import asyncpg

from topos.adapters.blob.s3 import S3BlobStore
from topos.adapters.db.pipeline_repo import PipelineRepo
from topos.adapters.geocode import geocode
from topos.adapters.llm import build_llm_client
from topos.adapters.ocr import extract_text
from topos.config import get_settings, is_placeholder_key
from topos.service.handlers import PipelineHandlers
from topos.service.pipeline import step
from topos.telemetry import configure_logging, get_logger

log = get_logger("worker")


async def main(*, drain: bool = False) -> None:
    """Run the pipeline claim loop.

    *drain* makes the worker exit as soon as the queue has no claimable work,
    instead of idling forever. That is the mode a batch job or an agent wants:
    "process what is pending, then give me my shell back".
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("worker.booting", db_dsn_configured=bool(settings.db_dsn), drain=drain)

    if not settings.db_dsn:
        log.error("worker.missing_dsn")
        return

    # Create connection pool
    pool = await asyncpg.create_pool(settings.db_dsn, min_size=1, max_size=5)
    repo = PipelineRepo(pool)

    # Build LLM Client
    llm_client = build_llm_client(settings, pool)

    # No usable API key -> mock client, so the pipeline still runs offline.
    # Loud, because silently fabricating claims is how synthetic rows ended up
    # indistinguishable from real ones.
    if is_placeholder_key(settings.llm_api_key):
        log.warning(
            "worker.llm_mock_mode",
            reason="TOPOS_LLM_API_KEY is unset or a placeholder",
            effect="claims are FABRICATED, not extracted from the document",
        )

        class MockLlmClient:
            async def complete(
                self,
                *,
                prompt: str,
                model: str,
                response_format: dict[str, object] | None = None,
                **kwargs: object,
            ) -> dict[str, object]:
                content = "[]"
                prompt_lower = prompt.lower()
                if "παπαναστασίου" in prompt_lower:
                    content = '[{"predicate": "road_damage", "value": {"street": "Παπαναστασίου", "description": "εκτεταμένες φθορές και λακκούβες"}, "span_start": 0, "span_end": 50, "confidence": 1.0}]'
                elif "τούμπας" in prompt_lower:
                    content = '[{"predicate": "power_outage", "value": {"neighbourhood": "Άνω Τούμπα", "duration": "08:00 - 14:00"}, "span_start": 0, "span_end": 50, "confidence": 1.0}]'
                elif "εγνατία" in prompt_lower:
                    match = re.search(r"εγνατία\s+(\w+)", prompt_lower)
                    suffix = match.group(1) if match else "45"
                    content = f'[{{"predicate": "water_leak", "value": {{"street": "Εγνατία {suffix}", "description": "σοβαρή βλάβη στον κεντρικό αγωγό ύδρευσης"}}, "span_start": 0, "span_end": 130, "confidence": 1.0}}]'
                else:
                    content = '[{"predicate": "road_damage", "value": {"street": "Τσιμισκή 12", "description": "καθίζηση οδοστρώματος"}, "span_start": 0, "span_end": 10, "confidence": 0.85}]'

                return {"choices": [{"message": {"content": content}}]}

        llm_client = MockLlmClient()

    blob = S3BlobStore(
        endpoint_url=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        access_key_id=settings.s3_access_key,
        secret_access_key=settings.s3_secret_key,
    )
    handlers = PipelineHandlers(pool, llm_client, geocode, blob, extract_text)

    shutdown_event = asyncio.Event()

    # Graceful shutdown handler
    def handle_signal() -> None:
        log.info("worker.shutting_down")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, handle_signal)

    log.info("worker.started")
    try:
        while not shutdown_event.is_set():
            # Claim one ready row, process with handlers, and advance.
            work_done = await step(repo, handlers.get_map())
            if work_done:
                # If we processed a row, check for more work immediately
                continue

            if drain:
                log.info("worker.drained")
                break

            # Queue was empty; sleep briefly and wait before checking again
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
    except Exception as exc:
        log.exception("worker.error", error=str(exc))
    finally:
        log.info("worker.cleaning_up")
        await pool.close()
        log.info("worker.stopped")


if __name__ == "__main__":
    with suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(main())
