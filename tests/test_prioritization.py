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
