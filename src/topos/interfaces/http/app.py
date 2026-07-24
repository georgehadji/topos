"""FastAPI app. Slice 0.3 gives /healthz; routers accrete per-slice (e.g. 0.12 artifacts)."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from topos.config import get_settings
from topos.interfaces.http.artifacts import router as artifacts_router
from topos.interfaces.http.graph import router as graph_router
from topos.interfaces.http.review import router as review_router
from topos.interfaces.http.search import router as search_router
from topos.telemetry import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Topos", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Prometheus metrics (slice 1.15)
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)
except ImportError:
    pass

app.include_router(graph_router)
app.include_router(artifacts_router)
app.include_router(search_router)
app.include_router(review_router)

# Mount built React SPA if available (must be last — catches all paths)
_web_dist = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "web", "dist")
if os.path.isdir(_web_dist):
    app.mount("/", StaticFiles(directory=_web_dist, html=True), name="web")
