"""FastAPI app. Slice 0.3 gives /healthz; routers accrete per-slice (e.g. 0.12 artifacts)."""

from __future__ import annotations

from fastapi import FastAPI

from topos.config import get_settings
from topos.telemetry import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Topos", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
