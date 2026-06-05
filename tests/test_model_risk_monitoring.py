from __future__ import annotations
from datetime import datetime
from aml_framework.engine.model_risk_monitoring import (
    build_model_risk_report,
)

GEN = datetime(2026, 6, 5)


def _inv(models):
    return {"models": models}


def _m(key, kind="rule", tier="high", owner="MLRO", cadence=12):
    return {"model_key": key, "kind": kind, "tier": tier, "owner": owner, "cadence_months": cadence}


def test_empty_inventory():
    r = build_model_risk_report(
        _inv([]), current_counts={}, prior_counts={}, drift_high_ratio=2.0, generated_at=GEN
    )
    assert r.entries == [] and r.n_models == 0 and r.n_high_drift == 0
    assert r.enabled is True and r.generated_at == GEN


def test_no_prior_is_unknown_drift():
    r = build_model_risk_report(
        _inv([_m("R1")]),
        current_counts={"R1": 5},
        prior_counts=None,
        drift_high_ratio=2.0,
        generated_at=GEN,
    )
    e = r.entries[0]
    assert e.drift == "unknown" and e.prior_alerts is None and e.current_alerts == 5
    assert e.drift_ratio is None


def test_high_drift_when_doubled():
    r = build_model_risk_report(
        _inv([_m("R1")]),
        current_counts={"R1": 20},
        prior_counts={"R1": 5},
        drift_high_ratio=2.0,
        generated_at=GEN,
    )
    e = r.entries[0]
    assert e.drift == "high" and e.drift_ratio == 4.0
    assert r.n_high_drift == 1


def test_high_drift_when_halved():
    r = build_model_risk_report(
        _inv([_m("R1")]),
        current_counts={"R1": 2},
        prior_counts={"R1": 10},
        drift_high_ratio=2.0,
        generated_at=GEN,
    )
    assert r.entries[0].drift == "high"  # 0.2 <= 1/2.0


def test_normal_drift_within_band():
    r = build_model_risk_report(
        _inv([_m("R1")]),
        current_counts={"R1": 6},
        prior_counts={"R1": 5},
        drift_high_ratio=2.0,
        generated_at=GEN,
    )
    assert r.entries[0].drift == "normal" and r.entries[0].drift_ratio == 1.2


def test_prior_zero_current_positive_is_high():
    r = build_model_risk_report(
        _inv([_m("R1")]),
        current_counts={"R1": 3},
        prior_counts={"R1": 0},
        drift_high_ratio=2.0,
        generated_at=GEN,
    )
    assert r.entries[0].drift == "high"


def test_prior_zero_current_zero_is_normal():
    r = build_model_risk_report(
        _inv([_m("R1")]),
        current_counts={"R1": 0},
        prior_counts={"R1": 0},
        drift_high_ratio=2.0,
        generated_at=GEN,
    )
    assert r.entries[0].drift == "normal"


def test_high_drift_sorted_first_then_tier_then_key():
    models = [_m("B", tier="low"), _m("A", tier="low"), _m("C", tier="high")]
    # B doubles (high), A and C normal
    r = build_model_risk_report(
        _inv(models),
        current_counts={"A": 5, "B": 20, "C": 5},
        prior_counts={"A": 5, "B": 5, "C": 5},
        drift_high_ratio=2.0,
        generated_at=GEN,
    )
    assert r.entries[0].model_key == "B"  # high drift first
    # remaining sorted by (tier, key): high<low so C(high) before A(low)
    assert [e.model_key for e in r.entries[1:]] == ["C", "A"]


def test_missing_count_defaults_zero():
    r = build_model_risk_report(
        _inv([_m("R1")]),
        current_counts={},
        prior_counts={"R1": 5},
        drift_high_ratio=2.0,
        generated_at=GEN,
    )
    assert r.entries[0].current_alerts == 0 and r.entries[0].drift == "high"


def test_deterministic():
    inv = _inv([_m("R1"), _m("R2")])
    cc = {"R1": 5, "R2": 10}
    pc = {"R1": 5, "R2": 10}
    a = build_model_risk_report(
        inv, current_counts=cc, prior_counts=pc, drift_high_ratio=2.0, generated_at=GEN
    )
    b = build_model_risk_report(
        inv, current_counts=cc, prior_counts=pc, drift_high_ratio=2.0, generated_at=GEN
    )
    assert a.model_dump() == b.model_dump()
