from __future__ import annotations

import pytest
from pydantic import ValidationError

from aml_framework.spec.models import ModelRiskMonitoring, Program


def _program(**kw):
    base = dict(
        name="P",
        jurisdiction="CA",
        regulator="FINTRAC",
        owner="MLRO",
        effective_date="2026-01-01",
    )
    base.update(kw)
    return Program(**base)


def test_program_defaults_model_risk_monitoring_none():
    assert _program().model_risk_monitoring is None


def test_valid_block_and_defaults():
    m = ModelRiskMonitoring(enabled=True)
    assert m.enabled is True
    assert m.drift_high_ratio == 2.0
    assert m.baseline_runs == 10
    p = _program(model_risk_monitoring=m)
    assert p.model_risk_monitoring.enabled is True


def test_default_disabled():
    assert ModelRiskMonitoring().enabled is False


def test_drift_high_ratio_must_be_ge_1():
    with pytest.raises(ValidationError):
        ModelRiskMonitoring(drift_high_ratio=0.5)


def test_drift_high_ratio_rejects_non_finite():
    with pytest.raises(ValidationError):
        ModelRiskMonitoring(drift_high_ratio=float("inf"))


def test_baseline_runs_must_be_ge_1():
    with pytest.raises(ValidationError):
        ModelRiskMonitoring(baseline_runs=0)


def test_extra_forbidden():
    with pytest.raises(ValidationError):
        ModelRiskMonitoring(enabled=True, bogus=1)
