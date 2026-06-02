from __future__ import annotations

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
