from __future__ import annotations
import pytest
from pydantic import ValidationError
from aml_framework.spec.models import Program, RiskSegment, RiskSegmentation


def _program(**kw):
    base = dict(
        name="P", jurisdiction="CA", regulator="FINTRAC", owner="MLRO", effective_date="2026-01-01"
    )
    base.update(kw)
    return Program(**base)


def test_program_defaults_risk_segmentation_none():
    assert _program().risk_segmentation is None


def test_valid_risk_segmentation_block():
    seg = RiskSegment(
        id="low_kyc",
        values=["low"],
        deprioritize_below=0.3,
        rationale="low-risk retail",
        owner="MLRO",
    )
    rs = RiskSegmentation(enabled=True, segments=[seg])
    p = _program(risk_segmentation=rs)
    assert p.risk_segmentation.enabled is True
    assert p.risk_segmentation.segments[0].field == "customer_risk_rating"
    assert p.risk_segmentation.segments[0].deprioritize_below == 0.3


def test_default_disabled_empty_segments():
    rs = RiskSegmentation()
    assert rs.enabled is False and rs.segments == []


def test_deprioritize_below_must_be_0_1():
    with pytest.raises(ValidationError):
        RiskSegment(id="x", values=["low"], deprioritize_below=1.5, rationale="r", owner="o")


def test_deprioritize_below_rejects_non_finite():
    with pytest.raises(ValidationError):
        RiskSegment(
            id="x", values=["low"], deprioritize_below=float("inf"), rationale="r", owner="o"
        )


def test_values_must_be_non_empty():
    with pytest.raises(ValidationError):
        RiskSegment(id="x", values=[], deprioritize_below=0.3, rationale="r", owner="o")


def test_extra_forbidden():
    with pytest.raises(ValidationError):
        RiskSegment(
            id="x", values=["low"], deprioritize_below=0.3, rationale="r", owner="o", bogus=1
        )


def test_field_rejects_unsupported_value():
    with pytest.raises(ValidationError):
        RiskSegment(
            id="x",
            field="some_other_col",
            values=["low"],
            deprioritize_below=0.3,
            rationale="r",
            owner="o",
        )
