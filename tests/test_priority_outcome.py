from __future__ import annotations

from types import SimpleNamespace

from aml_framework.engine.priority_outcome import (
    LEAKAGE_SAFE_FEATURES,
    build_priority_outcome,
    precision_at_k,
    recall_at_labels,
)
from aml_framework.spec.models import ProgramPrioritization


def _rule(rid="r1", severity="high", risk_tier=None):
    return SimpleNamespace(id=rid, severity=severity, risk_tier=risk_tier)


def _alert(cid, amount, count):
    return {"customer_id": cid, "rule_id": "r1", "sum_amount": amount, "count": count}


def test_precision_at_k_counts_true_positives_in_top_k():
    ranked = ["C0001", "C9999", "C0002", "C8888"]
    labels = {"C0001": True, "C0002": True}
    assert precision_at_k(ranked, labels, 2) == 0.5  # C0001 true, C9999 false
    assert precision_at_k(ranked, labels, 4) == 0.5  # 2 true of 4


def test_recall_counts_labelled_positives_surfaced():
    ranked = ["C0001", "C9999"]
    labels = {"C0001": True, "C0002": True}  # 2 positives, only C0001 surfaced
    assert recall_at_labels(ranked, labels) == 0.5


def test_build_outcome_champion_vs_challenger_deterministic():
    rule = _rule()
    alerts_by_rule = {
        "r1": [_alert("C0001", 90000, 9), _alert("C9999", 100, 1), _alert("C0002", 50000, 5)]
    }
    labels = {"C0001": True, "C0002": True, "C9999": False}
    champ = ProgramPrioritization(enabled=True)
    chall = ProgramPrioritization(enabled=True, weights={"amount": 5.0})
    rules = {"r1": rule}
    out_a = build_priority_outcome(alerts_by_rule, rules, labels, champion=champ, challenger=chall)
    out_b = build_priority_outcome(alerts_by_rule, rules, labels, champion=champ, challenger=chall)
    assert out_a.model_dump() == out_b.model_dump()  # deterministic
    assert out_a.n_alerts == 3
    assert out_a.n_labelled_positives == 2
    assert out_a.winner in ("champion", "challenger", "tie")
    assert set(out_a.champion.precision_at_k) == {"5", "10", "20"}


def test_leakage_allowlist_is_the_documented_feature_set():
    assert LEAKAGE_SAFE_FEATURES == frozenset({"sum_amount", "amount", "count", "matched_row_ids"})


def test_score_is_invariant_to_a_future_dated_field():
    from aml_framework.engine.prioritization import score_alert

    cfg = ProgramPrioritization(enabled=True)
    base = _alert("C0001", 90000, 9)
    leaked = {**base, "future_balance_next_month": 10_000_000, "as_of_plus_30d_count": 999}
    assert score_alert(base, _rule(), cfg).score == score_alert(leaked, _rule(), cfg).score


def test_load_labels_csv(tmp_path):
    from aml_framework.engine.priority_outcome import load_labels_csv

    p = tmp_path / "labels.csv"
    p.write_text("customer_id,is_true_positive\nC0001,true\nC9999,false\nC0002,1\n")
    labels = load_labels_csv(p)
    assert labels == {"C0001": True, "C9999": False, "C0002": True}
