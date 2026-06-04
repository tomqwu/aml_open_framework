from __future__ import annotations

import pytest

# Unit-test CI installs only `.[dev]` (no pandas); the Triage Queue helpers
# live behind the dashboard extra. Skip the whole module when pandas is
# absent — same guard as test_chart_helpers.py.
pd = pytest.importorskip("pandas")

from aml_framework.dashboard import triage  # noqa: E402


def _df(rows):
    return pd.DataFrame(rows)


def test_has_priority_true_when_column_present_and_scored():
    df = _df([{"rule_id": "r1", "customer_id": "C1", "priority_score": 0.8}])
    assert triage.has_priority(df) is True


def test_has_priority_false_when_column_absent():
    df = _df([{"rule_id": "r1", "customer_id": "C1"}])
    assert triage.has_priority(df) is False


def test_has_priority_false_when_empty():
    assert triage.has_priority(pd.DataFrame()) is False


def test_triage_view_sorted_desc_and_drops_unscored():
    df = _df(
        [
            {"rule_id": "r1", "customer_id": "C1", "severity": "low", "priority_score": 0.2},
            {"rule_id": "r2", "customer_id": "C2", "severity": "high", "priority_score": 0.9},
            {"rule_id": "r3", "customer_id": "C3", "severity": "high"},  # unscored -> NaN
        ]
    )
    view = triage.triage_view(df)
    scores = list(view["priority_score"])
    assert scores == sorted(scores, reverse=True)  # descending
    assert scores[0] == 0.9
    assert len(view) == 2  # the unscored row is dropped


def test_triage_view_stable_tiebreak_on_rule_then_customer():
    df = _df(
        [
            {"rule_id": "rB", "customer_id": "C2", "priority_score": 0.5},
            {"rule_id": "rA", "customer_id": "C9", "priority_score": 0.5},
            {"rule_id": "rA", "customer_id": "C1", "priority_score": 0.5},
        ]
    )
    view = triage.triage_view(df)
    pairs = list(zip(view["rule_id"], view["customer_id"]))
    assert pairs == [("rA", "C1"), ("rA", "C9"), ("rB", "C2")]


def test_explanation_rows_sorted_by_abs_contribution_desc_bias_first():
    explanation = [
        {"feature": "bias", "value": 1.0, "contribution": -1.0},
        {"feature": "severity", "value": 0.75, "contribution": 0.75},
        {"feature": "amount", "value": 0.10, "contribution": 0.05},
        {"feature": "volume", "value": 0.40, "contribution": 0.20},
    ]
    rows = triage.explanation_rows(explanation)
    feats = [r["feature"] for r in rows]
    # bias kept first (the baseline), then features by |contribution| desc
    assert feats[0] == "bias"
    assert feats[1:] == ["severity", "volume", "amount"]


def test_explanation_rows_handles_empty():
    assert triage.explanation_rows(None) == []
    assert triage.explanation_rows([]) == []


def test_alert_label_format():
    row = {"customer_id": "C1", "rule_id": "r1", "priority_score": 0.873}
    assert triage.alert_label(row) == "C1 · r1 · 0.87"
