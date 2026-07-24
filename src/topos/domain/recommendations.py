"""Recommendation engine: ranking + approval gate + export.

A recommendation is a scored, explainable suggestion for what the
policy office should act on. It requires human sign-off before
export (ARCHITECTURE.md L6).

Architecture (ARCHITECTURE.md §Scoring):
  recommendations = sorted(problems, key=priority) filtered by
  approval status. A recommendation is a problem with a score
  snapshot, a Greek explanation, and an approval state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A scored, explained, and approval-tracked recommendation."""

    problem_id: str
    title: str
    category: str
    priority: Decimal  # 0.0-1.0
    impact: Decimal | None
    urgency: Decimal | None
    explanation: str  # Greek text from slice 2.5
    status: str  # "pending", "approved", "rejected", "exported"
    approved_by: str | None
    approved_at: datetime | None
    exported_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExportPackage:
    """A signed-off recommendation ready for export.

    Contains everything needed for the policy office to act.
    """

    problem_id: str
    title: str
    priority: Decimal
    explanation: str
    supporting_claims: list[dict[str, Any]]
    approved_by: str
    approved_at: datetime
    exported_at: datetime
