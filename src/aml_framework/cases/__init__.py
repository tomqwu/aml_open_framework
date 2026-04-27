"""Case-management primitives.

The engine emits one case per alert; this package turns those raw cases
into the higher-level **investigation** units that FinCEN's effectiveness
rule treats as the unit of analyst work, and gives operators real-time
SLA + escalation visibility (the gap the FCA's Mar 2026 Dear CEO letter
on SAR backlogs called out).

Round 6 builds out: investigation aggregation (PR #61), multi-tenant
dashboard (PR #62), SLA timer + escalation engine (this PR), case-to-STR
auto-bundling, and a case dashboard page.
"""

from aml_framework.cases.aggregator import (
    Investigation,
    aggregate_investigations,
    bucket_window_for,
)
from aml_framework.cases.sla import (
    BacklogStats,
    EscalationAction,
    SLAStatus,
    apply_escalation,
    compute_sla_status,
    summarise_backlog,
)

__all__ = [
    "Investigation",
    "aggregate_investigations",
    "bucket_window_for",
    "BacklogStats",
    "EscalationAction",
    "SLAStatus",
    "apply_escalation",
    "compute_sla_status",
    "summarise_backlog",
]
