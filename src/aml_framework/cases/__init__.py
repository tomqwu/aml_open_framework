"""Case-management primitives.

The engine emits one case per alert; this package turns those raw cases
into the higher-level **investigation** units that FinCEN's effectiveness
rule treats as the unit of analyst work, gives operators real-time
SLA + escalation visibility (the gap the FCA's Mar 2026 Dear CEO letter
on SAR backlogs called out), and produces submission-ready ZIPs per
investigation (the Wolfsberg Feb 2026 correspondent-banking ask).

Round 6 builds out: investigation aggregation (PR #61), multi-tenant
dashboard (PR #62), SLA timer + escalation engine (PR #63),
case-to-STR auto-bundling (this PR), and a case dashboard page.
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
from aml_framework.cases.linkage import (
    LinkedCustomer,
    build_rule_domain_map,
    classify_rule_domain,
    find_linked_customers,
    linkage_summary,
)
from aml_framework.cases.str_bundle import (
    BUNDLE_VERSION,
    bundle_hash,
    bundle_investigation_to_str,
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
    "BUNDLE_VERSION",
    "bundle_hash",
    "bundle_investigation_to_str",
    "LinkedCustomer",
    "build_rule_domain_map",
    "classify_rule_domain",
    "find_linked_customers",
    "linkage_summary",
]
