"""Built-in trigger detectors.

Each detector is **pure**: same inputs produce the same triggers. The
engine builds a `ScanContext` once and hands it to every detector;
detectors don't share mutable state. New detectors plug in by
implementing the same protocol shape (callable returning list[Trigger]).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from aml_framework.pkyc.triggers import Severity, Trigger

if TYPE_CHECKING:
    from aml_framework.pkyc.scan import ScanContext


def _customer_name_index(
    customers: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Map UPPERCASED full_name → list of customers with that name.

    A list because real-world data has duplicate names; pKYC must flag
    every match, not just the first.
    """
    idx: dict[str, list[dict[str, Any]]] = {}
    for c in customers:
        name = str(c.get("full_name") or "").strip().upper()
        if name:
            idx.setdefault(name, []).append(c)
    return idx


class SanctionsHitDetector:
    """Flag customers whose name matches a *newly-added* sanctions entry.

    Reads from `context.sanctions_added` (the SyncResult.added list from
    PR #44). Only newly-added entries fire — matches against entries
    already on the list have presumably been reviewed at onboarding.
    """

    name = "sanctions_hit_detector"
    severity: Severity = "critical"

    def __init__(self, *, severity: Severity | None = None) -> None:
        if severity:
            self.severity = severity

    def detect(
        self,
        customers: list[dict[str, Any]],
        context: ScanContext,
    ) -> list[Trigger]:
        if not context.sanctions_added:
            return []
        idx = _customer_name_index(customers)
        triggers: list[Trigger] = []
        for entry in context.sanctions_added:
            entry_name = (entry.name or "").strip().upper()
            for cust in idx.get(entry_name, []):
                triggers.append(
                    Trigger(
                        customer_id=cust["customer_id"],
                        kind="sanctions_hit",
                        severity=self.severity,
                        evidence={
                            "matched_name": entry.name,
                            "list_source": entry.list_source,
                            "country": entry.country,
                            "list_id": entry.list_id,
                        },
                        recommended_action="escalate",
                        detector=self.name,
                        detected_at=context.as_of,
                    )
                )
        return triggers


class AdverseMediaDetector:
    """Flag customers whose name appears on the adverse-media list."""

    name = "adverse_media_detector"
    severity: Severity = "high"

    def __init__(self, *, severity: Severity | None = None) -> None:
        if severity:
            self.severity = severity

    def detect(
        self,
        customers: list[dict[str, Any]],
        context: ScanContext,
    ) -> list[Trigger]:
        if not context.adverse_media_entries:
            return []
        idx = _customer_name_index(customers)
        triggers: list[Trigger] = []
        for entry in context.adverse_media_entries:
            entry_name = (entry.name or "").strip().upper()
            for cust in idx.get(entry_name, []):
                triggers.append(
                    Trigger(
                        customer_id=cust["customer_id"],
                        kind="adverse_media",
                        severity=self.severity,
                        evidence={
                            "matched_name": entry.name,
                            "list_source": entry.list_source,
                        },
                        recommended_action="re_review",
                        detector=self.name,
                        detected_at=context.as_of,
                    )
                )
        return triggers


class CountryRiskDetector:
    """Flag customers based in a high-risk jurisdiction.

    The set is configurable so an institution can pass FATF black-list,
    FATF grey-list, or its own internal list. Grey-list moves often
    happen overnight; pKYC means the next scan flags affected customers
    without waiting for the calendar review.
    """

    name = "country_risk_detector"
    severity: Severity = "high"

    def __init__(self, *, severity: Severity | None = None) -> None:
        if severity:
            self.severity = severity

    def detect(
        self,
        customers: list[dict[str, Any]],
        context: ScanContext,
    ) -> list[Trigger]:
        if not context.high_risk_countries:
            return []
        targets = {c.upper() for c in context.high_risk_countries}
        triggers: list[Trigger] = []
        for cust in customers:
            country = str(cust.get("country") or "").upper()
            if country and country in targets:
                triggers.append(
                    Trigger(
                        customer_id=cust["customer_id"],
                        kind="country_risk",
                        severity=self.severity,
                        evidence={"country": country},
                        recommended_action="re_review",
                        detector=self.name,
                        detected_at=context.as_of,
                    )
                )
        return triggers


class TransactionPatternDetector:
    """Flag customers whose recent alert volume crosses a threshold.

    Composes with the existing rule engine: pass `recent_alerts_by_customer`
    (a `customer_id → alert_count` map computed by the caller from the
    latest run's audit ledger). Volume shifts often precede emerging
    typologies; pKYC catches them before the next calendar review.
    """

    name = "transaction_pattern_detector"
    severity: Severity = "medium"

    def __init__(self, *, threshold: int = 3, severity: Severity | None = None) -> None:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        self.threshold = threshold
        if severity:
            self.severity = severity

    def detect(
        self,
        customers: list[dict[str, Any]],
        context: ScanContext,
    ) -> list[Trigger]:
        if not context.recent_alerts_by_customer:
            return []
        triggers: list[Trigger] = []
        cust_ids = {c["customer_id"] for c in customers if "customer_id" in c}
        for cid, count in context.recent_alerts_by_customer.items():
            if cid not in cust_ids:
                continue
            if count >= self.threshold:
                triggers.append(
                    Trigger(
                        customer_id=cid,
                        kind="transaction_pattern",
                        severity=self.severity,
                        evidence={
                            "alert_count": count,
                            "threshold": self.threshold,
                            "lookback_days": context.lookback_days,
                        },
                        recommended_action="re_review",
                        detector=self.name,
                        detected_at=context.as_of,
                    )
                )
        return triggers


class StaleKYCDetector:
    """Calendar fallback — flag reviews that are past due.

    Severity is risk-rating-driven: high-risk customers overdue → high
    severity, medium → medium, low → low. The thresholds match common
    AML programme standards (high: 12mo, medium: 24mo, low: 36mo) but
    are configurable.
    """

    name = "stale_kyc_detector"

    def __init__(
        self,
        *,
        thresholds_days: dict[str, int] | None = None,
    ) -> None:
        self.thresholds_days = thresholds_days or {
            "critical": 180,
            "high": 365,
            "medium": 730,
            "low": 1095,
        }

    def detect(
        self,
        customers: list[dict[str, Any]],
        context: ScanContext,
    ) -> list[Trigger]:
        triggers: list[Trigger] = []
        for cust in customers:
            review_date = cust.get("last_kyc_review") or cust.get("kyc_review_date")
            if review_date is None:
                continue
            review_dt = _coerce_datetime(review_date)
            if review_dt is None:
                continue
            rating = str(cust.get("risk_rating") or "low").lower()
            limit_days = self.thresholds_days.get(rating, self.thresholds_days["low"])
            age = context.as_of - review_dt
            if age >= timedelta(days=limit_days):
                severity: Severity = "critical" if rating == "critical" else "low"
                # Match the customer's risk rating where possible so the
                # downstream recalculator doesn't artificially escalate.
                if rating in ("high", "medium", "low", "critical"):
                    severity = rating  # type: ignore[assignment]
                triggers.append(
                    Trigger(
                        customer_id=cust["customer_id"],
                        kind="stale_kyc",
                        severity=severity,
                        evidence={
                            "last_review": review_dt.isoformat(),
                            "age_days": age.days,
                            "threshold_days": limit_days,
                            "current_rating": rating,
                        },
                        recommended_action="re_review",
                        detector=self.name,
                        detected_at=context.as_of,
                    )
                )
        return triggers


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace(" ", "T", 1))
    except (TypeError, ValueError):
        return None
