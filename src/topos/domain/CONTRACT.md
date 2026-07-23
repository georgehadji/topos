# topos.domain — Contract

**Status:** Active. Updated with every slice.

**Responsibility:** Pure business logic. Zero IO, zero project imports. All functions are deterministic — no async, no clock reads, no randomness.

**Does:** Types, enums, value objects, scoring DAG fragments, pipeline state transitions, entity-resolution feature functions, Greek text normalisation.

**Does not:** Import anything from `topos.*` (enforced by import-linter contract `domain-purity`). Call `datetime.now()` — time is always a parameter.

**Test policy:** Pure-function tests with literal inputs and literal expected outputs. No mocks. No fixtures. No fixtures that need fixtures.

**Key files:**
- `types.py` — Ids, enums, `PipelineRow` dataclass
- `pipeline_fsm.py` — `next_state()` pure transition function
- `problem.py` — Problem status transition guard

**Known gaps:** Scoring DAG, entity-resolution features, Greek text normalisation — Phase 2.
