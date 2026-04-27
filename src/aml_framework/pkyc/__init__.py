"""Perpetual KYC (pKYC) trigger engine.

Traditional KYC reviews follow a fixed calendar (high-risk customers
every 12 months, medium every 24, low every 36-60). pKYC flips that:
**events** trigger re-review, not the clock. This package detects those
events and recomputes risk ratings.

Five built-in detectors in v1:
  - SanctionsHitDetector       : customer name matches a newly-added
                                 sanctions entry (consumes
                                 sanctions/SyncResult deltas from PR #44).
  - AdverseMediaDetector       : customer name appears on adverse-media
                                 list.
  - CountryRiskDetector        : customer jurisdiction is on a
                                 high-risk-jurisdictions list.
  - TransactionPatternDetector : customer triggered ≥ N alerts in the
                                 lookback window (volume/velocity shift).
  - StaleKYCDetector           : calendar fallback — review past due.

A RiskRecalculator composes the detected triggers into a new
risk_rating per customer. The caller decides whether to write the
new rating back to source (the engine is intentionally side-effect
free — it returns a TriggerScan).
"""

from aml_framework.pkyc.detectors import (
    AdverseMediaDetector,
    CountryRiskDetector,
    SanctionsHitDetector,
    StaleKYCDetector,
    TransactionPatternDetector,
)
from aml_framework.pkyc.recalculator import RiskRecalculator, recompute_rating
from aml_framework.pkyc.scan import ScanContext, TriggerScan, run_scan
from aml_framework.pkyc.triggers import Trigger, TriggerKind

__all__ = [
    "Trigger",
    "TriggerKind",
    "ScanContext",
    "TriggerScan",
    "run_scan",
    "RiskRecalculator",
    "recompute_rating",
    "SanctionsHitDetector",
    "AdverseMediaDetector",
    "CountryRiskDetector",
    "TransactionPatternDetector",
    "StaleKYCDetector",
]
