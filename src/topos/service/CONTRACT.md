# topos.service — Contract

**Status:** Active.

**Responsibility:** Orchestration layer. Coordinates adapters toward domain goals. Never imports a concrete adapter — depends on Protocols defined in `service/ports.py`.

**Does:** Import `topos.domain.*`. Define `typing.Protocol` ports. Wire adapters together. Drive the pipeline stepper.

**Does not:** Import `topos.adapters.*`, `fastapi`, `asyncpg`, `httpx` (enforced by import-linter).

**Test policy:** Unit tests for orchestration logic; contract tests for real adapter wiring. Pure domain functions passed through without re-testing.

**Key files:**
- `ports.py` — `Clock`, `BlobStore`, `LlmClient`, `PipelineRepo` Protocols
- `pipeline.py` — `step()` / `run_step()`: stepper loop

**Known gaps:** Review service — slice 1.x.
