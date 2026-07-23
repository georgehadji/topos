# topos.interfaces — Contract

**Status:** Active.

**Responsibility:** External entry points: HTTP routers and CLI commands. May import `topos.service` and `topos.domain`. Keeps web framework concerns (FastAPI) isolated from business logic.

**Does:** Define route handlers, CLI commands, request/response schemas, middleware.

**Does not:** Import `topos.adapters.*` directly — goes through service layer.

**Key files:**
- `http/app.py` — FastAPI app, `/healthz`
- `cli/worker.py` — Pipeline stepper entry point

**Known gaps:** Artifact/claim/problem endpoints — slice 0.12+.
