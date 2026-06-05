from __future__ import annotations
from aml_framework.engine.suppression import (  # noqa: F401 — public-surface import assertions
    SuppressionResult,
    score_suppression,
    stamp_suppression,
)
from aml_framework.spec.models import RiskSegment, RiskSegmentation


def _seg(**kw):
    base = dict(
        id="low_kyc",
        field="customer_risk_rating",
        values=["low"],
        deprioritize_below=0.3,
        rationale="r",
        owner="o",
    )
    base.update(kw)
    return RiskSegment(**base)


def _cfg(enabled=True, segments=None):
    return RiskSegmentation(enabled=enabled, segments=segments or [_seg()])


def test_match_and_low_score_is_suppressed():
    alert = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"}, True)
    assert alert["suppression"]["applied"] is True
    assert alert["suppression"]["segment_id"] == "low_kyc"
    assert alert["suppression"]["reversible"] is True
    assert alert["suppression"]["score"] == 0.1


def test_high_score_not_suppressed_even_in_segment():
    alert = {"customer_id": "C1", "priority_score": 0.9}
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"}, True)
    assert alert["suppression"]["applied"] is False


def test_customer_not_in_any_segment_not_suppressed():
    alert = {"customer_id": "C2", "priority_score": 0.1}
    stamp_suppression(None, [alert], _cfg(), {"C2": "high"}, True)
    assert alert["suppression"]["applied"] is False


def test_noop_when_disabled():
    alert = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [alert], _cfg(enabled=False), {"C1": "low"}, True)
    assert "suppression" not in alert


def test_noop_when_cfg_none():
    alert = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [alert], None, {"C1": "low"}, True)
    assert "suppression" not in alert


def test_missing_priority_score_records_precondition_reason():
    alert = {"customer_id": "C1"}
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"}, True)
    assert alert["suppression"]["applied"] is False
    assert "prioritization" in alert["suppression"]["reason"].lower()


def test_never_alters_existing_keys_or_disposition():
    alert = {"customer_id": "C1", "priority_score": 0.1, "disposition": "open", "queue": "L1"}
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"}, True)
    assert alert["disposition"] == "open" and alert["queue"] == "L1"


def test_deterministic():
    a1 = {"customer_id": "C1", "priority_score": 0.1}
    a2 = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [a1], _cfg(), {"C1": "low"}, True)
    stamp_suppression(None, [a2], _cfg(), {"C1": "low"}, True)
    assert a1["suppression"] == a2["suppression"]


def test_first_matching_segment_wins_deterministically():
    segs = [_seg(id="s1", deprioritize_below=0.2), _seg(id="s2", deprioritize_below=0.5)]
    alert = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [alert], _cfg(segments=segs), {"C1": "low"}, True)
    assert alert["suppression"]["segment_id"] == "s1"


def test_score_at_threshold_is_not_suppressed():
    # strict < threshold; equal is NOT suppressed
    alert = {"customer_id": "C1", "priority_score": 0.3}
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"}, True)
    assert alert["suppression"]["applied"] is False


def test_prioritization_disabled_forces_not_suppressed_even_with_score():
    # an alert that WOULD suppress (low score, in segment) is NOT suppressed when prioritization is off
    alert = {"customer_id": "C1", "priority_score": 0.1}
    stamp_suppression(None, [alert], _cfg(), {"C1": "low"}, False)
    assert alert["suppression"]["applied"] is False
    assert "prioritization disabled" in alert["suppression"]["reason"]
