"""Compliance-side tooling: regulation drift detection, examination prep.

Round-7 PR #1 ships `regwatch` — hashes every cited regulation URL across
all loaded specs and detects silent drift (e.g. FinCEN BOI was narrowed
in March 2025; downstream specs went stale without notice).

Future modules will follow the same pattern: defensive layers that sit
*above* the spec, not inside it.
"""

from aml_framework.compliance.boi import (
    DEFAULT_FRESHNESS_DAYS,
    BeneficialOwner,
    BOIRecord,
    boi_summary,
    derive_boi_status,
    derive_boi_status_for_all,
    export_fincen_boi,
    is_reporting_company,
    synthesise_owners_from_customer,
)
from aml_framework.compliance.regwatch import (
    DriftReport,
    RegwatchEntry,
    check_drift,
    citation_url,
    load_baseline,
    save_baseline,
    scan_spec,
)

__all__ = [
    "DriftReport",
    "RegwatchEntry",
    "check_drift",
    "citation_url",
    "load_baseline",
    "save_baseline",
    "scan_spec",
    "BeneficialOwner",
    "BOIRecord",
    "DEFAULT_FRESHNESS_DAYS",
    "boi_summary",
    "derive_boi_status",
    "derive_boi_status_for_all",
    "export_fincen_boi",
    "is_reporting_company",
    "synthesise_owners_from_customer",
]
