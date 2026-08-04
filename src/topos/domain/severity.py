"""Per-category severity baselines.

`MeasuredInputs.severity` has no measured source: nothing in a council-minute
PDF states how bad a problem is on a 0-1 scale, and asking an LLM to invent
one per document would make the number unstable between runs of the same
input. So severity here is an explicit, versioned **policy** — the same kind
of artefact as the authority alias table, and reviewable the same way.

It is a baseline, not a verdict. It answers "how bad is this *class* of
problem, other things equal", and the rest of the DAG moves the final priority
around it using things that *are* measured: how many independent sources
reported it (reach), how confident the extractor was (evidence), what it costs
to fix.

Editing these numbers changes what a politician is told to care about first.
That is a political judgement, not a technical one, so it lives in one visible
table with a version string rather than being scattered through the scorer.
Bump ``BASELINE_VER`` on any change so old snapshots remain interpretable.
"""

from __future__ import annotations

from decimal import Decimal

__all__ = ["BASELINE_VER", "DEFAULT_SEVERITY", "severity_for"]

BASELINE_VER = "1.0.0"

# Ordering rationale, briefly: immediate risk to life and health first, then
# loss of an essential utility, then things that degrade daily life, then
# administrative and procedural failures. Categories are the predicates the
# extractor emits (see service/extraction.py's prompt).
_SEVERITY: dict[str, Decimal] = {
    # Life-safety
    "pedestrian_hazard_remediation_delay": Decimal("0.80"),
    "building_collapse_risk": Decimal("0.95"),
    "flooding": Decimal("0.85"),
    "fire_risk": Decimal("0.85"),
    "road_damage": Decimal("0.65"),
    # Essential utilities
    "water_supply_disruption": Decimal("0.70"),
    "power_outage": Decimal("0.65"),
    "sewage_overflow": Decimal("0.80"),
    # Health and environment
    "waste_accumulation": Decimal("0.60"),
    "pollution": Decimal("0.70"),
    "waste_management_infrastructure_planning": Decimal("0.35"),
    # Daily life
    "public_transport_disruption": Decimal("0.55"),
    "road_congestion": Decimal("0.40"),
    "public_space_maintenance_delay": Decimal("0.35"),
    "green_space_damage": Decimal("0.35"),
    # Education
    "school_maintenance_delay": Decimal("0.60"),
    "school_relocation_delay": Decimal("0.55"),
    # Administrative / procedural
    "tender_failure_repeat": Decimal("0.45"),
    "administrative_delay": Decimal("0.30"),
    "procurement_irregularity": Decimal("0.50"),
}

# Used for any predicate not in the table. Deliberately mid-scale: an unknown
# category should neither dominate the ranking nor vanish from it, and a new
# predicate appearing here is a signal to classify it, not to guess low.
DEFAULT_SEVERITY = Decimal("0.50")


def severity_for(category: str) -> Decimal:
    """Baseline severity for a problem category, or the neutral default."""
    return _SEVERITY.get(category, DEFAULT_SEVERITY)
