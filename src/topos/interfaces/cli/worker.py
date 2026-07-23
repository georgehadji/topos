"""Worker entrypoint: `python -m topos.interfaces.cli.worker`. Stepper loop lands in slice 0.8.

STUB — deliberately does nothing yet beyond proving the process boots and
logs. Do not fake a claim loop ahead of the real pipeline_repo (slice 0.8).
"""

from __future__ import annotations

import asyncio

from topos.config import get_settings
from topos.telemetry import configure_logging, get_logger


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("worker")
    log.info("worker.boot", db_dsn_configured=bool(settings.db_dsn))
    # Slice 0.8 replaces this with the SKIP LOCKED claim loop (ARCHITECTURE.md > pipeline).
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
