"""Case-management primitives.

The engine emits one case per alert; this package turns those raw cases
into the higher-level **investigation** units that FinCEN's effectiveness
rule treats as the unit of analyst work, and that downstream metrics +
STR bundling key on.

Round 6 builds out: investigation aggregation (this PR), SLA timer +
escalation, case-to-STR auto-bundling, and a case dashboard page.
"""

from aml_framework.cases.aggregator import (
    Investigation,
    aggregate_investigations,
    bucket_window_for,
)

__all__ = [
    "Investigation",
    "aggregate_investigations",
    "bucket_window_for",
]
