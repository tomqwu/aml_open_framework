"""Beneficial Ownership (BOI) workflow primitives.

Process problem this solves
---------------------------
The KYC analyst doing entity onboarding today re-keys the same
beneficial-owner roster into 3+ systems: CRM, AML monitoring, and the
FinCEN BOI return (or the equivalent FINTRAC / EU return). Each system
has a different schema. The data drifts the moment one of them is
edited and not the others. The result: the BOI on file with FinCEN is
not the BOI the AML monitoring system thinks it has, and the analyst
can't tell which is right without re-collecting from the customer.

This module exists so the framework's customer-360 + pKYC data is
**the** source of truth for BOI; the dashboard page composes it into a
status view; and the export produces a FinCEN-format payload directly
— no rekeying.

Scope kept narrow on purpose: BOI status derivation + FinCEN-format
export. Not a full ownership-graph engine; that would belong in a
larger entity-resolution module.

Refresher on the regulatory shape (post Mar-2025 narrowing):
- FinCEN BOI applies to "reporting companies" — primarily US-formed
  domestic entities and registered foreign entities. Most banks file
  on customers' behalf only when contractually obliged.
- A beneficial owner is any individual who exercises substantial
  control OR owns ≥ 25% of the entity.
- Reports must be refreshed when ownership changes; FinCEN's
  cadence guidance settled at "within 30 days of a change".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

BOIStatus = Literal["current", "stale", "missing", "not_required"]

# Default freshness window — FinCEN's 30-day rule on ownership changes
# is event-driven, not time-driven, but most institutions still treat
# annual review as the floor. Pick whichever is stricter for your jurisdiction.
DEFAULT_FRESHNESS_DAYS = 365


@dataclass(frozen=True)
class BeneficialOwner:
    """One beneficial owner of a reporting-company customer.

    Field names mirror FinCEN's BOI Report (FinCEN BOIR) schema so the
    export is one mapping step, not a translation layer.
    """

    full_name: str
    date_of_birth: str  # YYYY-MM-DD
    residential_address: str
    identification_type: str  # "passport" | "drivers_license" | "state_id" | "foreign_id"
    identification_number: str
    identification_jurisdiction: str  # ISO 3166-1 alpha-2
    ownership_pct: float | None = None  # nullable for substantial-control-only
    is_substantial_control: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "date_of_birth": self.date_of_birth,
            "residential_address": self.residential_address,
            "identification": {
                "type": self.identification_type,
                "number": self.identification_number,
                "jurisdiction": self.identification_jurisdiction,
            },
            "ownership_pct": self.ownership_pct,
            "is_substantial_control": self.is_substantial_control,
        }


@dataclass(frozen=True)
class BOIRecord:
    """A customer's full BOI state — used by the dashboard panel."""

    customer_id: str
    entity_name: str
    status: BOIStatus
    last_review: datetime | None
    days_since_review: int | None
    owners: list[BeneficialOwner] = field(default_factory=list)
    reason: str = ""  # human-readable status explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "entity_name": self.entity_name,
            "status": self.status,
            "last_review": self.last_review.isoformat() if self.last_review else None,
            "days_since_review": self.days_since_review,
            "owner_count": len(self.owners),
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Reporting-company gating + status derivation
# ---------------------------------------------------------------------------


def is_reporting_company(customer: dict[str, Any]) -> bool:
    """Heuristic: a customer is a reporting company when they have a
    declared `business_activity` (i.e. they're an entity, not an
    individual). Real implementations should consult the entity-type
    field on the customer record once the spec carries it.
    """
    return bool(customer.get("business_activity"))


def derive_boi_status(
    customer: dict[str, Any],
    *,
    as_of: datetime,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> BOIRecord:
    """Compute one customer's BOI status as of `as_of`."""
    cid = customer.get("customer_id", "")
    name = customer.get("full_name") or cid

    if not is_reporting_company(customer):
        return BOIRecord(
            customer_id=cid,
            entity_name=name,
            status="not_required",
            last_review=None,
            days_since_review=None,
            reason="Not a reporting company (no business_activity declared).",
        )

    last = customer.get("boi_last_review") or customer.get("edd_last_review")
    if not isinstance(last, datetime):
        return BOIRecord(
            customer_id=cid,
            entity_name=name,
            status="missing",
            last_review=None,
            days_since_review=None,
            reason="No BOI review on file.",
        )

    age = (as_of - last).days
    if age <= freshness_days:
        return BOIRecord(
            customer_id=cid,
            entity_name=name,
            status="current",
            last_review=last,
            days_since_review=age,
            reason=f"Reviewed {age} day(s) ago.",
        )
    return BOIRecord(
        customer_id=cid,
        entity_name=name,
        status="stale",
        last_review=last,
        days_since_review=age,
        reason=f"Last reviewed {age} day(s) ago — exceeds {freshness_days}-day freshness window.",
    )


def derive_boi_status_for_all(
    customers: list[dict[str, Any]],
    *,
    as_of: datetime,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> list[BOIRecord]:
    """Apply `derive_boi_status` over every customer, sorted worst-first."""
    records = [derive_boi_status(c, as_of=as_of, freshness_days=freshness_days) for c in customers]
    rank = {"missing": 0, "stale": 1, "current": 2, "not_required": 3}
    records.sort(key=lambda r: (rank.get(r.status, 99), r.customer_id))
    return records


# ---------------------------------------------------------------------------
# FinCEN BOI export
# ---------------------------------------------------------------------------


def export_fincen_boi(
    customer: dict[str, Any],
    owners: list[BeneficialOwner],
    *,
    filing_type: str = "initial",
    filed_at: datetime | None = None,
) -> dict[str, Any]:
    """Format one customer's BOI as a FinCEN BOIR-shaped payload.

    `filing_type` ∈ {"initial", "updated", "corrected", "newly_exempt"}.
    The output is JSON-ready; the FinCEN portal accepts it after the
    institution wraps it with the filing transmission envelope.
    """
    return {
        "filing_type": filing_type,
        "filed_at": (filed_at or datetime.utcnow()).isoformat(),
        "reporting_company": {
            "customer_id": customer.get("customer_id", ""),
            "legal_name": customer.get("full_name", ""),
            "country_of_formation": customer.get("country", ""),
            "business_activity": customer.get("business_activity", ""),
        },
        "beneficial_owners": [o.to_dict() for o in owners],
        "owner_count": len(owners),
        "schema": "fincen_boir_v1",
    }


def boi_summary(records: list[BOIRecord]) -> dict[str, int]:
    """One-line counts for the dashboard KPI strip."""
    summary = {"missing": 0, "stale": 0, "current": 0, "not_required": 0}
    for r in records:
        summary[r.status] = summary.get(r.status, 0) + 1
    return summary


# ---------------------------------------------------------------------------
# Demo helper
# ---------------------------------------------------------------------------


def synthesise_owners_from_customer(customer: dict[str, Any]) -> list[BeneficialOwner]:
    """Stub one beneficial-owner record per customer for demo/test use.

    Real onboarding flows should populate this from the customer's KYC
    file or from a third-party provider (Ondato, Fenergo, Trulioo). The
    dashboard's export button uses this to keep the demo end-to-end
    runnable without external integrations.
    """
    return [
        BeneficialOwner(
            full_name=customer.get("full_name", ""),
            date_of_birth=(
                (customer.get("onboarded_at") or datetime.utcnow()) - timedelta(days=365 * 40)
            )
            .date()
            .isoformat(),
            residential_address=f"on file ({customer.get('country', '')})",
            identification_type="passport",
            identification_number=f"P-{customer.get('customer_id', '')}",
            identification_jurisdiction=customer.get("country", ""),
            ownership_pct=100.0,
            is_substantial_control=True,
        )
    ]
