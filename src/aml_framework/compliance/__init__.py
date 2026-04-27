"""Compliance-side tooling: regulation drift detection, examination prep.

Round-7 PR #1 ships `regwatch` — hashes every cited regulation URL across
all loaded specs and detects silent drift (e.g. FinCEN BOI was narrowed
in March 2025; downstream specs went stale without notice).

Future modules will follow the same pattern: defensive layers that sit
*above* the spec, not inside it.
"""

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
]
