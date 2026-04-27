"""pKYC trigger engine tests — detectors, recalculator, scan orchestrator.

All tests run against synthetic dict customers — no engine, no IO.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aml_framework.pkyc import (
    AdverseMediaDetector,
    CountryRiskDetector,
    ScanContext,
    SanctionsHitDetector,
    StaleKYCDetector,
    TransactionPatternDetector,
    Trigger,
    recompute_rating,
    run_scan,
)
from aml_framework.sanctions.base import SanctionEntry


def _now():
    return datetime(2026, 4, 27, tzinfo=timezone.utc)


def _customer(
    cid="C0001",
    name="ALICE NEWMAN",
    country="US",
    rating="low",
    last_review=None,
):
    out = {
        "customer_id": cid,
        "full_name": name,
        "country": country,
        "risk_rating": rating,
    }
    if last_review is not None:
        out["last_kyc_review"] = last_review
    return out


# ---------------------------------------------------------------------------
# Trigger model
# ---------------------------------------------------------------------------


class TestTriggerModel:
    def test_extra_forbidden(self):
        with pytest.raises(Exception):
            Trigger(
                customer_id="C1",
                kind="sanctions_hit",
                severity="high",
                bogus="x",  # type: ignore[call-arg]
            )

    def test_kind_enum_enforced(self):
        with pytest.raises(Exception):
            Trigger(customer_id="C1", kind="not_a_kind", severity="high")  # type: ignore[arg-type]

    def test_severity_enum_enforced(self):
        with pytest.raises(Exception):
            Trigger(customer_id="C1", kind="sanctions_hit", severity="extreme")  # type: ignore[arg-type]

    def test_default_recommended_action(self):
        t = Trigger(customer_id="C1", kind="stale_kyc", severity="low")
        assert t.recommended_action == "re_review"


# ---------------------------------------------------------------------------
# SanctionsHitDetector
# ---------------------------------------------------------------------------


class TestSanctionsHitDetector:
    def test_fires_on_newly_added_match(self):
        ctx = ScanContext(
            as_of=_now(),
            sanctions_added=[
                SanctionEntry(name="ALICE NEWMAN", list_source="OFAC_SDN", country="US")
            ],
        )
        triggers = SanctionsHitDetector().detect([_customer()], ctx)
        assert len(triggers) == 1
        t = triggers[0]
        assert t.kind == "sanctions_hit"
        assert t.severity == "critical"
        assert t.recommended_action == "escalate"
        assert t.evidence["list_source"] == "OFAC_SDN"

    def test_no_fire_when_no_added_entries(self):
        ctx = ScanContext(as_of=_now(), sanctions_added=[])
        assert SanctionsHitDetector().detect([_customer()], ctx) == []

    def test_case_insensitive_match(self):
        ctx = ScanContext(
            as_of=_now(),
            sanctions_added=[SanctionEntry(name="alice newman", list_source="EU_CONSOL")],
        )
        triggers = SanctionsHitDetector().detect([_customer()], ctx)
        assert len(triggers) == 1

    def test_duplicate_names_both_flagged(self):
        ctx = ScanContext(
            as_of=_now(),
            sanctions_added=[SanctionEntry(name="JOHN DOE", list_source="OFAC_SDN")],
        )
        custs = [
            _customer(cid="C1", name="JOHN DOE"),
            _customer(cid="C2", name="JOHN DOE"),
        ]
        triggers = SanctionsHitDetector().detect(custs, ctx)
        assert {t.customer_id for t in triggers} == {"C1", "C2"}

    def test_severity_override(self):
        ctx = ScanContext(
            as_of=_now(),
            sanctions_added=[SanctionEntry(name="ALICE NEWMAN", list_source="OFAC_SDN")],
        )
        triggers = SanctionsHitDetector(severity="high").detect([_customer()], ctx)
        assert triggers[0].severity == "high"


# ---------------------------------------------------------------------------
# AdverseMediaDetector
# ---------------------------------------------------------------------------


class TestAdverseMediaDetector:
    def test_fires_on_match(self):
        ctx = ScanContext(
            as_of=_now(),
            adverse_media_entries=[SanctionEntry(name="ALICE NEWMAN", list_source="ADVERSE_MEDIA")],
        )
        triggers = AdverseMediaDetector().detect([_customer()], ctx)
        assert len(triggers) == 1
        assert triggers[0].kind == "adverse_media"
        assert triggers[0].severity == "high"

    def test_no_fire_when_no_entries(self):
        ctx = ScanContext(as_of=_now())
        assert AdverseMediaDetector().detect([_customer()], ctx) == []


# ---------------------------------------------------------------------------
# CountryRiskDetector
# ---------------------------------------------------------------------------


class TestCountryRiskDetector:
    def test_fires_when_country_in_high_risk(self):
        ctx = ScanContext(as_of=_now(), high_risk_countries={"RU", "KP"})
        triggers = CountryRiskDetector().detect(
            [_customer(country="RU"), _customer(cid="C2", country="US")], ctx
        )
        assert len(triggers) == 1
        assert triggers[0].customer_id == "C0001"
        assert triggers[0].evidence["country"] == "RU"

    def test_no_fire_when_no_list(self):
        ctx = ScanContext(as_of=_now(), high_risk_countries=set())
        assert CountryRiskDetector().detect([_customer(country="RU")], ctx) == []

    def test_case_insensitive(self):
        ctx = ScanContext(as_of=_now(), high_risk_countries={"ru"})
        triggers = CountryRiskDetector().detect([_customer(country="RU")], ctx)
        assert len(triggers) == 1


# ---------------------------------------------------------------------------
# TransactionPatternDetector
# ---------------------------------------------------------------------------


class TestTransactionPatternDetector:
    def test_threshold_validation(self):
        with pytest.raises(ValueError):
            TransactionPatternDetector(threshold=0)

    def test_fires_above_threshold(self):
        ctx = ScanContext(
            as_of=_now(),
            recent_alerts_by_customer={"C0001": 5, "C0002": 1},
            lookback_days=90,
        )
        triggers = TransactionPatternDetector(threshold=3).detect(
            [_customer(), _customer(cid="C0002", name="BOB")], ctx
        )
        assert len(triggers) == 1
        assert triggers[0].customer_id == "C0001"
        assert triggers[0].evidence["alert_count"] == 5

    def test_no_fire_below_threshold(self):
        ctx = ScanContext(
            as_of=_now(),
            recent_alerts_by_customer={"C0001": 2},
        )
        assert TransactionPatternDetector(threshold=3).detect([_customer()], ctx) == []

    def test_unknown_customer_ignored(self):
        ctx = ScanContext(
            as_of=_now(),
            recent_alerts_by_customer={"GHOST": 10},
        )
        assert TransactionPatternDetector(threshold=3).detect([_customer()], ctx) == []


# ---------------------------------------------------------------------------
# StaleKYCDetector
# ---------------------------------------------------------------------------


class TestStaleKYCDetector:
    def test_overdue_high_risk_fires(self):
        old_date = _now() - timedelta(days=400)  # > 365d threshold for high
        ctx = ScanContext(as_of=_now())
        cust = _customer(rating="high", last_review=old_date)
        triggers = StaleKYCDetector().detect([cust], ctx)
        assert len(triggers) == 1
        assert triggers[0].kind == "stale_kyc"
        assert triggers[0].severity == "high"
        assert triggers[0].evidence["age_days"] == 400

    def test_not_overdue_no_trigger(self):
        recent = _now() - timedelta(days=100)
        ctx = ScanContext(as_of=_now())
        cust = _customer(rating="high", last_review=recent)
        assert StaleKYCDetector().detect([cust], ctx) == []

    def test_no_review_date_skipped(self):
        ctx = ScanContext(as_of=_now())
        assert StaleKYCDetector().detect([_customer()], ctx) == []

    def test_low_risk_longer_threshold(self):
        # 1095d threshold for low; 1200d should fire.
        old = _now() - timedelta(days=1200)
        ctx = ScanContext(as_of=_now())
        cust = _customer(rating="low", last_review=old)
        assert len(StaleKYCDetector().detect([cust], ctx)) == 1

    def test_iso_string_date_supported(self):
        old_iso = (_now() - timedelta(days=400)).isoformat()
        ctx = ScanContext(as_of=_now())
        cust = _customer(rating="high", last_review=old_iso)
        assert len(StaleKYCDetector().detect([cust], ctx)) == 1


# ---------------------------------------------------------------------------
# RiskRecalculator
# ---------------------------------------------------------------------------


def _trigger(severity, kind="sanctions_hit", cid="C0001"):
    return Trigger(customer_id=cid, kind=kind, severity=severity)


class TestRiskRecalculator:
    def test_no_triggers_no_change(self):
        assert recompute_rating({"risk_rating": "low"}, []) == "low"
        assert recompute_rating({"risk_rating": "high"}, []) == "high"

    def test_critical_trigger_jumps_to_critical(self):
        assert recompute_rating({"risk_rating": "low"}, [_trigger("critical")]) == "critical"

    def test_one_high_bumps_one_step(self):
        assert recompute_rating({"risk_rating": "low"}, [_trigger("high")]) == "medium"
        assert recompute_rating({"risk_rating": "medium"}, [_trigger("high")]) == "high"

    def test_high_caps_at_high_not_critical(self):
        # bumping from high should stop at high — only critical triggers reach critical
        assert recompute_rating({"risk_rating": "high"}, [_trigger("high")]) == "high"

    def test_two_mediums_bump(self):
        triggers = [_trigger("medium", kind="adverse_media"), _trigger("medium")]
        assert recompute_rating({"risk_rating": "low"}, triggers) == "medium"

    def test_one_medium_no_bump(self):
        assert recompute_rating({"risk_rating": "low"}, [_trigger("medium")]) == "low"

    def test_unknown_current_rating_treated_as_low(self):
        assert recompute_rating({"risk_rating": "weird"}, [_trigger("high")]) == "medium"


# ---------------------------------------------------------------------------
# Scan orchestrator
# ---------------------------------------------------------------------------


class TestScan:
    def test_aggregates_triggers_from_all_detectors(self):
        ctx = ScanContext(
            as_of=_now(),
            sanctions_added=[SanctionEntry(name="ALICE NEWMAN", list_source="OFAC_SDN")],
            high_risk_countries={"RU"},
            recent_alerts_by_customer={"C0001": 5},
            lookback_days=90,
        )
        cust = _customer(country="RU", rating="low")
        scan = run_scan([cust], ctx)
        kinds = {t.kind for t in scan.triggers}
        assert "sanctions_hit" in kinds
        assert "country_risk" in kinds
        assert "transaction_pattern" in kinds

    def test_rating_change_recorded(self):
        ctx = ScanContext(
            as_of=_now(),
            sanctions_added=[SanctionEntry(name="ALICE NEWMAN", list_source="OFAC_SDN")],
        )
        scan = run_scan([_customer(rating="low")], ctx)
        assert len(scan.rating_changes) == 1
        rc = scan.rating_changes[0]
        assert rc.old_rating == "low"
        assert rc.new_rating == "critical"

    def test_no_change_when_no_triggers(self):
        ctx = ScanContext(as_of=_now())
        scan = run_scan([_customer()], ctx)
        assert scan.triggers == []
        assert scan.rating_changes == []

    def test_to_dict_serialisable(self):
        ctx = ScanContext(
            as_of=_now(),
            sanctions_added=[SanctionEntry(name="ALICE NEWMAN", list_source="OFAC_SDN")],
        )
        scan = run_scan([_customer()], ctx)
        d = scan.to_dict()
        assert d["customers_scanned"] == 1
        assert isinstance(d["triggers"], list)
        # Round-trip through json to ensure serialisable.
        import json as _json

        _json.dumps(d, default=str)

    def test_custom_detectors_only(self):
        ctx = ScanContext(as_of=_now(), high_risk_countries={"RU"})
        scan = run_scan([_customer(country="RU")], ctx, detectors=[CountryRiskDetector()])
        assert scan.detectors_run == ["country_risk_detector"]
        assert all(t.kind == "country_risk" for t in scan.triggers)

    def test_detectors_run_listed(self):
        ctx = ScanContext(as_of=_now())
        scan = run_scan([_customer()], ctx)
        assert "sanctions_hit_detector" in scan.detectors_run
        assert "stale_kyc_detector" in scan.detectors_run


# ---------------------------------------------------------------------------
# Composition with sanctions package (PR #44)
# ---------------------------------------------------------------------------


class TestSanctionsIntegration:
    def test_sync_result_added_feeds_detector(self, tmp_path):
        from aml_framework.sanctions import SanctionsCache, SanctionEntry as SE

        # Write a baseline list, then "sync" with a new entry that matches a customer.
        cache = SanctionsCache(lists_dir=tmp_path)
        cache.write("ofac", [SE(name="OLD ENTRY", list_source="OFAC_SDN")])
        new_result = cache.write(
            "ofac",
            [
                SE(name="OLD ENTRY", list_source="OFAC_SDN"),
                SE(name="ALICE NEWMAN", list_source="OFAC_SDN", country="US"),
            ],
        )
        assert [e.name for e in new_result.added] == ["ALICE NEWMAN"]

        ctx = ScanContext(as_of=_now(), sanctions_added=list(new_result.added))
        scan = run_scan([_customer()], ctx)
        sanctions_triggers = [t for t in scan.triggers if t.kind == "sanctions_hit"]
        assert len(sanctions_triggers) == 1
        assert sanctions_triggers[0].evidence["matched_name"] == "ALICE NEWMAN"
