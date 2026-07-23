"""Protocols that adapters satisfy structurally. service/ imports these, never
a concrete adapter class. See ARCHITECTURE.md > Layering and .importlinter
contract `service-ports-only`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from topos.domain.pipeline_fsm import StepOutcome
from topos.domain.types import ArtifactId, PipelineRow, PipelineState


class Clock(Protocol):
    """Injected so domain/service code never calls datetime.now() directly."""

    def now(self) -> datetime: ...


class BlobStore(Protocol):
    """Content-addressed object storage. Implemented by adapters.blob.s3 (slice 0.9)."""

    async def put(self, key: str, data: bytes, *, content_type: str) -> str: ...
    async def get(self, key: str) -> bytes: ...


class LlmClient(Protocol):
    """See ARCHITECTURE.md > LLM usage. Implemented by adapters.llm (slice 0.10)."""

    async def complete(self, *, prompt: str, model: str, schema: type) -> object: ...


class PipelineRepo(Protocol):
    """Pipeline claim + transition persistence. Implemented by adapters.db.pipeline_repo
    (slice 0.8). The claim query uses SKIP LOCKED for concurrent worker safety.
    """

    async def claim_next(self) -> PipelineRow | None:
        """Atomically claim one ready row with SKIP LOCKED. Returns None if queue is empty."""
        ...

    async def advance(
        self,
        artifact_id: ArtifactId,
        *,
        from_state: PipelineState,
        outcome: StepOutcome,
        error: str | None = None,
    ) -> None:
        """Commit a transition. `from_state` is needed to distinguish advance
        (state changed) from retry (state unchanged).
        """
        ...

    async def release(self, artifact_id: ArtifactId) -> None:
        """Release the lock on a row without advancing state (e.g. shutdown)."""
        ...
