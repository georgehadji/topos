"""Shared value objects, ids, and enums.

Pure. No IO, no async, no clock reads, no randomness, no imports from other
topos.* packages. See ARCHITECTURE.md > Layering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID

ArtifactId = NewType("ArtifactId", UUID)
ProblemId = NewType("ProblemId", UUID)
ClaimId = NewType("ClaimId", UUID)
AuthorityId = NewType("AuthorityId", UUID)
SourceId = NewType("SourceId", str)


class PipelineState(StrEnum):
    """See ARCHITECTURE.md > The pipeline. Transition table lives in pipeline_fsm.py."""

    FETCHED = "fetched"
    TEXTIFIED = "textified"
    CHUNKED = "chunked"
    EXTRACTED = "extracted"
    GEOCODED = "geocoded"
    RESOLVED = "resolved"
    INDEXED = "indexed"
    DONE = "done"
    PARKED = "parked"


class GeoGranularity(StrEnum):
    """Geocoding never returns a bare point (ARCHITECTURE.md > Greek). This is drawn in the UI."""

    ADDRESS = "address"
    STREET = "street"
    BLOCK = "block"
    NEIGHBOURHOOD = "neighbourhood"
    MUNICIPALITY = "municipality"


class ProblemStatus(StrEnum):
    CANDIDATE = "candidate"
    CORROBORATED = "corroborated"
    VERIFIED = "verified"
    TRACKED = "tracked"
    ACTED_UPON = "acted_upon"
    RESOLVED = "resolved"
    RECURRING = "recurring"


@dataclass(frozen=True, slots=True)
class PipelineRow:
    """A row returned by the SKIP LOCKED claim query. Read-only snapshot."""

    artifact_id: ArtifactId
    state: PipelineState
    attempts: int
    run_after: datetime
    locked_until: datetime | None
    last_error: str | None
