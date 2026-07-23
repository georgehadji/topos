# topos.adapters — Contract

**Status:** Active.

**Responsibility:** Concrete IO implementations of `service.ports` Protocols. One subpackage per adapter backend. Each adapter satisfies its Protocol structurally — no adapter imports another.

**Does:** Import `topos.domain.*`. Use raw SQL, S3 API, HTTP clients.

**Does not:** Import another `topos.adapters.*` subpackage (enforced by import-linter contract `adapters-independent`). Import `topos.service.*` or `topos.interfaces.*`.

**Test policy:** Contract tests against real infrastructure (PostgreSQL, MinIO). Unit tests for edge cases with mocked transport.

**Subpackages:**
- `db/` — Raw SQL via `asyncpg`. Repositories return domain types.
- `blob/` — `S3BlobStore` via `aioboto3` against S3/MinIO.
- `llm/` — `LlmClient` decorator stack (Phase 0.10, **blocked on Q1**).
- `http/` — Outbound HTTP wrappers for source collectors (Phase 1).
- `geocode/` — Geocoding chain (Phase 1).
- `ocr/` — OCR pipeline (Phase 2).
- `stt/` — Speech-to-text (Phase 3).
- `sources/` — `SourcePlugin` base class + `SourceRegistry`.
