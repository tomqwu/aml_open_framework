from __future__ import annotations

from aml_framework.engine.suppression import (  # noqa: F401 — public-surface import assertions
    SuppressionReport,
    build_suppression_report,
)


def _suppressed(cid, seg="low_kyc", score=0.1):
    return {
        "customer_id": cid,
        "priority_score": score,
        "suppression": {
            "applied": True,
            "segment_id": seg,
            "reason": f"score {score} < 0.3 for segment '{seg}'",
            "threshold": 0.3,
            "score": score,
            "reversible": True,
        },
    }


def _not_suppressed(cid, seg=None, score=0.9):
    return {
        "customer_id": cid,
        "priority_score": score,
        "suppression": {
            "applied": False,
            "segment_id": seg,
            "reason": "score high",
            "threshold": 0.3 if seg else None,
            "score": score,
            "reversible": True,
        },
    }


def test_disabled_is_empty():
    report = build_suppression_report({}, enabled=False)
    assert report.enabled is False
    assert report.scored_alerts == 0
    assert report.suppressed == 0
    assert report.by_segment == {}
    assert report.by_rule == {}
    assert report.sample == []


def test_counts_correct_for_fixture():
    alerts_by_rule = {
        "rule_a": [_suppressed("C1"), _not_suppressed("C2", seg="low_kyc")],
        "rule_b": [_suppressed("C3"), _suppressed("C4", seg="dormant")],
    }
    report = build_suppression_report(alerts_by_rule, enabled=True)
    assert report.enabled is True
    # all four alerts carry a suppression dict -> all four scored
    assert report.scored_alerts == 4
    assert report.suppressed == 3
    assert report.by_segment == {"dormant": 1, "low_kyc": 2}
    assert report.by_rule == {"rule_a": 1, "rule_b": 2}
    assert len(report.sample) == 3


def test_alerts_without_suppression_dict_not_counted():
    alerts_by_rule = {
        "rule_a": [
            {"customer_id": "C1", "priority_score": 0.1},  # never stamped
            _suppressed("C2"),
        ],
    }
    report = build_suppression_report(alerts_by_rule, enabled=True)
    assert report.scored_alerts == 1
    assert report.suppressed == 1


def test_customer_id_masked_when_fn_passed():
    alerts_by_rule = {"rule_a": [_suppressed("C1"), _suppressed("C2")]}
    report = build_suppression_report(
        alerts_by_rule, enabled=True, mask_customer_id=lambda c: f"MASK::{c}"
    )
    sample_cids = {row["customer_id"] for row in report.sample}
    assert sample_cids == {"MASK::C1", "MASK::C2"}
    # raw ids must never appear when masking is enabled
    blob = report.model_dump_json()
    assert "C1" not in blob.replace("MASK::C1", "")
    assert "C2" not in blob.replace("MASK::C2", "")


def test_no_raw_customer_id_when_masking_enabled():
    alerts_by_rule = {"rule_a": [_suppressed("SECRET")]}
    report = build_suppression_report(alerts_by_rule, enabled=True, mask_customer_id=lambda c: "X")
    assert "SECRET" not in report.model_dump_json()


def test_deterministic_model_dump_equality():
    alerts_by_rule = {
        "rule_b": [_suppressed("C9"), _suppressed("C3")],
        "rule_a": [_suppressed("C5")],
    }
    r1 = build_suppression_report(alerts_by_rule, enabled=True)
    r2 = build_suppression_report(alerts_by_rule, enabled=True)
    assert r1.model_dump() == r2.model_dump()
    assert r1.model_dump_json() == r2.model_dump_json()


def test_report_is_frozen():
    report = build_suppression_report({}, enabled=False)
    import pytest

    with pytest.raises(Exception):
        report.suppressed = 5
