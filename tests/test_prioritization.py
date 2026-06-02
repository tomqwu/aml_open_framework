from __future__ import annotations

import math

import pytest
from aml_framework.spec.models import ProgramPrioritization


def test_prioritization_defaults_and_validation():
    p = ProgramPrioritization()
    assert p.enabled is False  # off by default
    assert p.weights.severity >= 0 and p.weights.amount >= 0
    custom = ProgramPrioritization(enabled=True, weights={"severity": 2.0, "amount": 0.5})
    assert custom.enabled is True
    assert custom.weights.severity == 2.0
    with pytest.raises(Exception):
        ProgramPrioritization(bogus=1)


from aml_framework.engine.prioritization import score_alert  # noqa: E402


def _rule(severity="high", risk_tier=None):
    from types import SimpleNamespace

    return SimpleNamespace(id="r1", severity=severity, risk_tier=risk_tier)


def test_score_in_unit_interval_and_explained():
    cfg = ProgramPrioritization(enabled=True)
    alert = {"customer_id": "C1", "sum_amount": 25000, "count": 6}
    res = score_alert(alert, _rule("high"), cfg)
    assert 0.0 <= res.score <= 1.0
    logit = sum(c["contribution"] for c in res.explanation)
    assert abs(res.score - 1.0 / (1.0 + math.exp(-logit))) < 1e-9
    assert {c["feature"] for c in res.explanation} >= {"severity", "amount", "volume"}


def test_higher_severity_scores_higher():
    cfg = ProgramPrioritization(enabled=True)
    alert = {"customer_id": "C1", "sum_amount": 1000, "count": 1}
    lo = score_alert(alert, _rule("low"), cfg).score
    hi = score_alert(alert, _rule("critical"), cfg).score
    assert hi > lo


def test_deterministic():
    cfg = ProgramPrioritization(enabled=True)
    alert = {"customer_id": "C1", "sum_amount": 9999.5, "count": 3}
    a = score_alert(alert, _rule("medium"), cfg)
    b = score_alert(alert, _rule("medium"), cfg)
    assert a.score == b.score and a.explanation == b.explanation


from aml_framework.engine.prioritization import stamp_priority  # noqa: E402


def test_stamp_priority_adds_fields_and_preserves_others():
    cfg = ProgramPrioritization(enabled=True)
    alerts = [
        {"customer_id": "C1", "rule_id": "r1", "sum_amount": 50000, "count": 8},
        {"customer_id": "C2", "rule_id": "r1", "sum_amount": 100, "count": 1},
    ]
    stamp_priority(_rule("high"), alerts, cfg)
    for a in alerts:
        assert 0.0 <= a["priority_score"] <= 1.0
        assert isinstance(a["priority_explanation"], list) and a["priority_explanation"]
        assert a["customer_id"] in {"C1", "C2"}
    assert alerts[0]["priority_score"] > alerts[1]["priority_score"]


def test_stamp_priority_noop_when_disabled():
    cfg = ProgramPrioritization(enabled=False)
    alerts = [{"customer_id": "C1", "rule_id": "r1", "sum_amount": 50000, "count": 8}]
    stamp_priority(_rule("high"), alerts, cfg)
    assert "priority_score" not in alerts[0]


def test_stamp_priority_noop_when_config_none():
    alerts = [{"customer_id": "C1", "rule_id": "r1", "sum_amount": 50000, "count": 8}]
    stamp_priority(_rule("high"), alerts, None)
    assert "priority_score" not in alerts[0]


from aml_framework.engine.prioritization import build_priority_report  # noqa: E402


def test_priority_report_summary():
    by_rule = {
        "r1": [
            {"customer_id": "C1", "priority_score": 0.9},
            {"customer_id": "C2", "priority_score": 0.2},
        ],
        "r2": [{"customer_id": "C3", "priority_score": 0.5}],
    }
    report = build_priority_report(by_rule, enabled=True, top_n=2)
    assert report.enabled is True
    assert report.scored_alerts == 3
    assert [t["customer_id"] for t in report.top_alerts] == ["C1", "C3"]
    assert (
        report.model_dump_json()
        == build_priority_report(by_rule, enabled=True, top_n=2).model_dump_json()
    )


def test_priority_report_empty_when_disabled():
    report = build_priority_report({}, enabled=False, top_n=2)
    assert report.enabled is False and report.scored_alerts == 0
