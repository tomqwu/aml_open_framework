"""High-level scan orchestrator — bundles detectors + recalculator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from aml_framework.pkyc.detectors import (
    AdverseMediaDetector,
    CountryRiskDetector,
    SanctionsHitDetector,
    StaleKYCDetector,
    TransactionPatternDetector,
)
from aml_framework.pkyc.recalculator import recompute_rating
from aml_framework.pkyc.triggers import Trigger
from aml_framework.sanctions.base import SanctionEntry


@dataclass(frozen=True)
class ScanContext:
    """Inputs every detector reads from. Build once, share across detectors."""

    as_of: datetime
    sanctions_added: list[SanctionEntry] = field(default_factory=list)
    adverse_media_entries: list[SanctionEntry] = field(default_factory=list)
    high_risk_countries: set[str] = field(default_factory=set)
    recent_alerts_by_customer: dict[str, int] = field(default_factory=dict)
    lookback_days: int = 90


@dataclass(frozen=True)
class RatingChange:
    customer_id: str
    old_rating: str
    new_rating: str
    triggers: list[Trigger]


@dataclass(frozen=True)
class TriggerScan:
    """Scan output — every trigger fired and every customer whose rating moved."""

    triggers: list[Trigger]
    rating_changes: list[RatingChange]
    customers_scanned: int
    detectors_run: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "customers_scanned": self.customers_scanned,
            "detectors_run": self.detectors_run,
            "triggers": [t.model_dump(mode="json") for t in self.triggers],
            "rating_changes": [
                {
                    "customer_id": rc.customer_id,
                    "old_rating": rc.old_rating,
                    "new_rating": rc.new_rating,
                    "trigger_count": len(rc.triggers),
                }
                for rc in self.rating_changes
            ],
        }


def _default_detectors() -> list:
    return [
        SanctionsHitDetector(),
        AdverseMediaDetector(),
        CountryRiskDetector(),
        TransactionPatternDetector(),
        StaleKYCDetector(),
    ]


def run_scan(
    customers: list[dict[str, Any]],
    context: ScanContext,
    *,
    detectors: Iterable | None = None,
) -> TriggerScan:
    """Run every detector, then recompute risk for affected customers.

    Pure function: no IO, no source writes. The caller takes the
    `rating_changes` and decides whether to persist.
    """
    detector_list = list(detectors) if detectors is not None else _default_detectors()

    all_triggers: list[Trigger] = []
    for det in detector_list:
        all_triggers.extend(det.detect(customers, context))

    by_customer: dict[str, list[Trigger]] = {}
    for t in all_triggers:
        by_customer.setdefault(t.customer_id, []).append(t)

    customers_by_id = {c["customer_id"]: c for c in customers if "customer_id" in c}

    changes: list[RatingChange] = []
    for cid, triggers in sorted(by_customer.items()):
        cust = customers_by_id.get(cid)
        if cust is None:
            continue
        old_rating = str(cust.get("risk_rating") or "low").lower()
        new_rating = recompute_rating(cust, triggers)
        if new_rating != old_rating:
            changes.append(
                RatingChange(
                    customer_id=cid,
                    old_rating=old_rating,
                    new_rating=new_rating,
                    triggers=list(triggers),
                )
            )

    return TriggerScan(
        triggers=all_triggers,
        rating_changes=changes,
        customers_scanned=len(customers),
        detectors_run=[d.name for d in detector_list],
    )


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)
