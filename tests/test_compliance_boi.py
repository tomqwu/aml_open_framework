"""Tests for `compliance/boi.py` — BOI status derivation + FinCEN export.

The KYC-onboarding analyst use case this guards: one source of truth
for beneficial-owner status; FinCEN-format export with no rekeying.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from aml_framework.compliance.boi import (
    DEFAULT_FRESHNESS_DAYS,
    BeneficialOwner,
    boi_summary,
    derive_boi_status,
    derive_boi_status_for_all,
    export_fincen_boi,
    is_reporting_company,
)


def _customer(
    cid: str = "C0001",
    business_activity: str = "import_export",
    last_review: datetime | None = None,
    name: str = "Acme Co",
    country: str = "US",
) -> dict:
    return {
        "customer_id": cid,
        "full_name": name,
        "country": country,
        "business_activity": business_activity,
        "edd_last_review": last_review,
        "boi_last_review": None,
    }


# ---------------------------------------------------------------------------
# Reporting-company gating
# ---------------------------------------------------------------------------


def test_reporting_company_when_business_activity_present() -> None:
    assert is_reporting_company(_customer(business_activity="manufacturing"))


def test_individual_when_business_activity_blank() -> None:
    assert not is_reporting_company(_customer(business_activity=""))


# ---------------------------------------------------------------------------
# Status derivation
# ---------------------------------------------------------------------------


def test_individual_returns_not_required() -> None:
    rec = derive_boi_status(_customer(business_activity=""), as_of=datetime(2026, 4, 28))
    assert rec.status == "not_required"
    assert rec.last_review is None


def test_reporting_company_with_no_review_is_missing() -> None:
    rec = derive_boi_status(_customer(last_review=None), as_of=datetime(2026, 4, 28))
    assert rec.status == "missing"
    assert rec.last_review is None
    assert "No BOI review" in rec.reason


def test_recent_review_is_current() -> None:
    as_of = datetime(2026, 4, 28)
    rec = derive_boi_status(
        _customer(last_review=as_of - timedelta(days=30)), as_of=as_of, freshness_days=365
    )
    assert rec.status == "current"
    assert rec.days_since_review == 30


def test_review_past_freshness_window_is_stale() -> None:
    as_of = datetime(2026, 4, 28)
    rec = derive_boi_status(
        _customer(last_review=as_of - timedelta(days=400)), as_of=as_of, freshness_days=365
    )
    assert rec.status == "stale"
    assert rec.days_since_review == 400


def test_freshness_window_default_is_365() -> None:
    assert DEFAULT_FRESHNESS_DAYS == 365


def test_boi_uses_dedicated_field_when_present() -> None:
    """When `boi_last_review` is set it wins over `edd_last_review`."""
    as_of = datetime(2026, 4, 28)
    cust = _customer(last_review=as_of - timedelta(days=400))
    cust["boi_last_review"] = as_of - timedelta(days=10)
    rec = derive_boi_status(cust, as_of=as_of)
    assert rec.status == "current"
    assert rec.days_since_review == 10


# ---------------------------------------------------------------------------
# Bulk + summary
# ---------------------------------------------------------------------------


def test_derive_status_for_all_is_sorted_worst_first() -> None:
    as_of = datetime(2026, 4, 28)
    customers = [
        _customer(cid="C001", last_review=as_of - timedelta(days=10)),  # current
        _customer(cid="C002", last_review=None),  # missing
        _customer(cid="C003", last_review=as_of - timedelta(days=400)),  # stale
        _customer(cid="C004", business_activity=""),  # not_required
    ]
    out = derive_boi_status_for_all(customers, as_of=as_of)
    assert [r.status for r in out] == ["missing", "stale", "current", "not_required"]


def test_summary_counts_each_status() -> None:
    as_of = datetime(2026, 4, 28)
    customers = [
        _customer(cid="C001", last_review=as_of - timedelta(days=10)),
        _customer(cid="C002", last_review=as_of - timedelta(days=10)),
        _customer(cid="C003", last_review=None),
        _customer(cid="C004", business_activity=""),
    ]
    out = derive_boi_status_for_all(customers, as_of=as_of)
    s = boi_summary(out)
    assert s["current"] == 2
    assert s["missing"] == 1
    assert s["not_required"] == 1
    assert s["stale"] == 0


# ---------------------------------------------------------------------------
# FinCEN export
# ---------------------------------------------------------------------------


def test_export_payload_has_required_top_level_fields() -> None:
    customer = _customer()
    owners = [
        BeneficialOwner(
            full_name="Jane Doe",
            date_of_birth="1980-01-15",
            residential_address="123 Elm St",
            identification_type="passport",
            identification_number="P-1234",
            identification_jurisdiction="US",
            ownership_pct=50.0,
        )
    ]
    payload = export_fincen_boi(customer, owners)
    assert payload["filing_type"] == "initial"
    assert payload["schema"] == "fincen_boir_v1"
    assert payload["reporting_company"]["legal_name"] == "Acme Co"
    assert payload["owner_count"] == 1
    assert payload["beneficial_owners"][0]["identification"]["type"] == "passport"


def test_export_filing_type_override() -> None:
    payload = export_fincen_boi(_customer(), [], filing_type="updated")
    assert payload["filing_type"] == "updated"


@pytest.mark.parametrize("filing_type", ["initial", "updated", "corrected", "newly_exempt"])
def test_export_accepts_all_fincen_filing_types(filing_type: str) -> None:
    payload = export_fincen_boi(_customer(), [], filing_type=filing_type)
    assert payload["filing_type"] == filing_type
