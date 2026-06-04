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


def test_precision_at_k_edge_cases():
    labels = {"C0001": True, "C0002": True}
    assert precision_at_k([], labels, 5) == 0.0  # empty ranking
    assert precision_at_k(["C0001"], {}, 5) == 0.0  # no positives
    assert precision_at_k(["C0001"], labels, 0) == 0.0  # k=0 guarded
    # k > len(ranking): denominator is k (textbook), not the slice length.
    assert precision_at_k(["C0001", "C0002"], labels, 20) == round(2 / 20, 6)


def test_outcome_score_ignores_non_allowlisted_alert_fields():
    # A post-as_of field riding on the alert must not change the backtest
    # score — the builder filters to LEAKAGE_SAFE_FEATURES before scoring.
    rule = _rule()
    clean = {"r1": [_alert("C0001", 90000, 9)]}
    leaked = {"r1": [{**_alert("C0001", 90000, 9), "future_balance": 10_000_000}]}
    labels = {"C0001": True}
    cfg = ProgramPrioritization(enabled=True)
    a = build_priority_outcome(clean, {"r1": rule}, labels, champion=cfg, challenger=cfg)
    b = build_priority_outcome(leaked, {"r1": rule}, labels, champion=cfg, challenger=cfg)
    assert a.champion.mean_score == b.champion.mean_score


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


def _prio_spec_and_labels(tmp_path):
    import pathlib

    s = pathlib.Path("examples/community_bank/aml.yaml").read_text()
    s = s.replace(
        "  effective_date: 2026-01-01\n",
        "  effective_date: 2026-01-01\n  prioritization:\n    enabled: true\n",
        1,
    )
    spec = tmp_path / "p.yaml"
    spec.write_text(s)
    labels = tmp_path / "labels.csv"
    labels.write_text("customer_id,is_true_positive\nC0001,true\nC0002,true\n")
    return spec, labels


def _run_with_labels(tmp_path, spec, labels, artifacts):
    from typer.testing import CliRunner

    from aml_framework.cli import app

    res = CliRunner().invoke(
        app,
        [
            "run",
            str(spec),
            "--seed",
            "42",
            "--as-of",
            "2026-02-01T00:00:00",
            "--artifacts",
            str(artifacts),
            "--labels",
            str(labels),
        ],
    )
    assert res.exit_code == 0, res.output
    return sorted(artifacts.glob("run-*"))[-1]


def test_priority_outcome_written_pinned_and_frozen(tmp_path):
    import json
    import os

    spec, labels = _prio_spec_and_labels(tmp_path)
    run_dir = _run_with_labels(tmp_path, spec, labels, tmp_path / "a")
    oc = run_dir / "priority_outcome.json"
    assert oc.exists()
    data = json.loads(oc.read_text())
    assert data["winner"] in ("champion", "challenger", "tie")
    assert data["n_labelled_positives"] == 2
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest.get("priority_outcome_hash")
    if os.name != "nt":
        assert (os.stat(oc).st_mode & 0o222) == 0  # frozen read-only


def test_priority_outcome_absent_without_labels(tmp_path):
    import pathlib

    s = pathlib.Path("examples/community_bank/aml.yaml").read_text()
    s = s.replace(
        "  effective_date: 2026-01-01\n",
        "  effective_date: 2026-01-01\n  prioritization:\n    enabled: true\n",
        1,
    )
    spec = tmp_path / "p.yaml"
    spec.write_text(s)
    from typer.testing import CliRunner

    from aml_framework.cli import app

    res = CliRunner().invoke(
        app, ["run", str(spec), "--seed", "42", "--artifacts", str(tmp_path / "a")]
    )
    assert res.exit_code == 0, res.output
    run_dir = sorted((tmp_path / "a").glob("run-*"))[-1]
    assert not (run_dir / "priority_outcome.json").exists()  # no labels -> no artifact


def test_priority_outcome_hash_deterministic_across_runs(tmp_path):
    import json

    spec, labels = _prio_spec_and_labels(tmp_path)
    rd1 = _run_with_labels(tmp_path, spec, labels, tmp_path / "a")
    rd2 = _run_with_labels(tmp_path, spec, labels, tmp_path / "b")
    h1 = json.loads((rd1 / "manifest.json").read_text())["priority_outcome_hash"]
    h2 = json.loads((rd2 / "manifest.json").read_text())["priority_outcome_hash"]
    assert h1 == h2  # same spec+seed+as_of+labels -> byte-identical outcome
