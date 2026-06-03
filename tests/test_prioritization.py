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


from datetime import datetime  # noqa: F401, E402  (may already be imported; dedupe if so)
from pathlib import Path  # noqa: E402

from typer.testing import CliRunner  # noqa: E402

from aml_framework.cli import app  # noqa: E402

SPEC = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def _run(tmp_path, spec_text=None, *, as_of: str | None = None):
    runner = CliRunner()
    spec = SPEC
    if spec_text is not None:
        spec = tmp_path / "aml.yaml"
        spec.write_text(spec_text, encoding="utf-8")
    cmd = ["run", str(spec), "--seed", "42", "--artifacts", str(tmp_path / "art")]
    if as_of is not None:
        cmd += ["--as-of", as_of]
    res = runner.invoke(app, cmd)
    assert res.exit_code == 0, res.output
    return sorted((tmp_path / "art").glob("run-*"))[-1]


def test_runner_stamps_priority_when_enabled(tmp_path):
    import json

    import yaml

    base = yaml.safe_load(SPEC.read_text())
    base["program"]["prioritization"] = {"enabled": True}
    run_dir = _run(tmp_path, yaml.safe_dump(base))
    report = run_dir / "priority_report.json"
    assert report.exists()
    data = json.loads(report.read_text())
    assert data["enabled"] is True and data["scored_alerts"] > 0
    any_scored = False
    for f in (run_dir / "alerts").glob("*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip() and "priority_score" in json.loads(line):
                any_scored = True
    assert any_scored


def test_runner_no_priority_when_absent(tmp_path):
    import json

    run_dir = _run(tmp_path)
    assert not (run_dir / "priority_report.json").exists()
    for f in (run_dir / "alerts").glob("*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip():
                assert "priority_score" not in json.loads(line)


def test_priority_report_is_manifest_pinned_and_frozen(tmp_path):
    import json
    import os

    import yaml

    base = yaml.safe_load(SPEC.read_text())
    base["program"]["prioritization"] = {"enabled": True}
    run_dir = _run(tmp_path, yaml.safe_dump(base))
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest.get("priority_report_hash"), "priority_report_hash must be pinned"
    if os.name != "nt":
        assert (os.stat(run_dir / "priority_report.json").st_mode & 0o222) == 0


_FIXED_AS_OF = "2026-04-23T12:00:00"


def test_prioritization_is_deterministic_across_runs(tmp_path):
    import json
    import yaml

    base = yaml.safe_load(SPEC.read_text())
    base["program"]["prioritization"] = {"enabled": True}
    text = yaml.safe_dump(base)
    p_a = tmp_path / "a"
    p_b = tmp_path / "b"
    p_a.mkdir()
    p_b.mkdir()
    rd1 = _run(p_a, text, as_of=_FIXED_AS_OF)
    rd2 = _run(p_b, text, as_of=_FIXED_AS_OF)
    m1 = json.loads((rd1 / "manifest.json").read_text())
    m2 = json.loads((rd2 / "manifest.json").read_text())
    assert m1["decisions_hash"] == m2["decisions_hash"]  # determinism contract intact
    # the priority artifact itself is byte-stable across runs (where score
    # non-determinism would actually show up — decisions_hash never carries it)
    assert m1["priority_report_hash"] == m2["priority_report_hash"] and m1["priority_report_hash"]


def test_prioritization_does_not_change_dispositions(tmp_path):
    import json
    import yaml

    # Both runs use the SAME yaml-roundtripped base, differing ONLY in the
    # prioritization block — otherwise the raw-vs-roundtripped spec would
    # alter rule serialisation (hence rule_version) and mask the real check.
    base = yaml.safe_load(SPEC.read_text())
    off_spec = yaml.safe_dump(base)
    on_base = yaml.safe_load(SPEC.read_text())
    on_base["program"]["prioritization"] = {"enabled": True}
    on_spec = yaml.safe_dump(on_base)
    p_off = tmp_path / "off"
    p_on = tmp_path / "on"
    p_off.mkdir()
    p_on.mkdir()
    off = _run(p_off, off_spec, as_of=_FIXED_AS_OF)
    on = _run(p_on, on_spec, as_of=_FIXED_AS_OF)

    def case_dispositions(rd):
        out = {}
        for f in sorted((rd / "cases").glob("*.json")):
            c = json.loads(f.read_text())
            out[c["case_id"]] = (c.get("rule_id"), c.get("queue"), c.get("status"))
        return out

    assert case_dispositions(off) == case_dispositions(on)

    # Stronger: the ONLY change to each case is the two added keys on the
    # embedded alert — strip them and every case file is byte-identical.
    def cases_minus_priority(rd):
        out = {}
        for f in sorted((rd / "cases").glob("*.json")):
            c = json.loads(f.read_text())
            alert = c.get("alert")
            if isinstance(alert, dict):
                alert.pop("priority_score", None)
                alert.pop("priority_explanation", None)
            out[c["case_id"]] = c
        return out

    assert cases_minus_priority(off) == cases_minus_priority(on)


def test_priority_report_does_not_leak_plaintext_customer_id_under_masking(tmp_path, monkeypatch):
    """P1 regression: priority_report.json is built from the in-memory (un-masked)
    alerts, so under AML_PII_MASKING=1 it must mask customer_id the same way
    alerts/*.jsonl does — never persisting a plaintext id."""
    import json
    import re

    import yaml

    monkeypatch.setenv("AML_PII_MASKING", "1")
    base = yaml.safe_load(SPEC.read_text())
    base["program"]["prioritization"] = {"enabled": True}
    p = tmp_path / "masked"
    p.mkdir()
    run_dir = _run(p, yaml.safe_dump(base), as_of=_FIXED_AS_OF)

    report = json.loads((run_dir / "priority_report.json").read_text())
    assert report["top_alerts"], "expected scored alerts to summarise"
    raw = re.compile(r"^C\d{4}$")  # community_bank plaintext customer_id shape
    hex16 = re.compile(r"^[0-9a-f]{16}$")  # ledger mask shape
    # Collect the masked ids the ledger wrote to alerts/*.jsonl.
    masked_in_alerts = set()
    for f in (run_dir / "alerts").glob("*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip():
                masked_in_alerts.add(json.loads(line).get("customer_id"))
    for t in report["top_alerts"]:
        cid = t["customer_id"]
        assert not raw.match(cid), f"plaintext customer_id leaked into report: {cid}"
        assert hex16.match(cid), f"expected masked 16-hex id, got {cid!r}"
        assert cid in masked_in_alerts, "report mask must match the alerts/*.jsonl mask"


def test_prioritization_change_surfaces_in_spec_diff(tmp_path):
    """Codex P2: a prioritization-only change (enabled toggle or weight tweak)
    must appear in compute_spec_diff().program_changes — governed triage
    scoring is regulator-facing and can't be invisible to reviewers."""
    import yaml

    from aml_framework.diff import compute_spec_diff

    raw = yaml.safe_load(SPEC.read_text())
    raw_a = {**raw, "program": {**raw["program"], "prioritization": {"enabled": True}}}
    raw_b = {
        **raw,
        "program": {
            **raw["program"],
            "prioritization": {"enabled": True, "weights": {"severity": 3.0}},
        },
    }
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text(yaml.safe_dump(raw_a))
    b.write_text(yaml.safe_dump(raw_b))
    weight_changes = [
        c for c in compute_spec_diff(a, b).program_changes if c.field.startswith("prioritization.")
    ]
    assert any(c.field == "prioritization.weights.severity" for c in weight_changes), weight_changes

    # enabled toggle also surfaces
    raw_c = {**raw, "program": {**raw["program"], "prioritization": {"enabled": False}}}
    c_path = tmp_path / "c.yaml"
    c_path.write_text(yaml.safe_dump(raw_c))
    toggle_changes = compute_spec_diff(c_path, a).program_changes
    assert any(c.field == "prioritization.enabled" for c in toggle_changes)


def test_scorer_tolerates_non_numeric_features():
    """Advisory invariant: a custom_sql/python_ref alert may carry a
    formatted/redacted sum_amount or count — scoring must NOT raise/abort."""
    cfg = ProgramPrioritization(enabled=True)
    res = score_alert({"sum_amount": "1,234.56", "count": "many"}, _rule("high"), cfg)
    assert 0.0 <= res.score <= 1.0
    feats = {c["feature"]: c["value"] for c in res.explanation if c["feature"] != "bias"}
    assert feats["amount"] == 0.0 and feats["volume"] == 0.0  # unparseable -> 0


def test_field_lineage_includes_priority_fields_when_enabled(tmp_path):
    """field_lineage.jsonl must account for the persisted priority fields so
    an auditor can trace the governed score back to program.prioritization."""
    import json

    import yaml

    base = yaml.safe_load(SPEC.read_text())
    base["program"]["prioritization"] = {"enabled": True}
    run_dir = _run(tmp_path, yaml.safe_dump(base))
    lineage = [
        json.loads(line)
        for line in (run_dir / "field_lineage.jsonl").read_text().splitlines()
        if line.strip()
    ]
    fields = {e["alert_field"] for e in lineage}
    assert {"priority_score", "priority_explanation"} <= fields
    prio_rows = [e for e in lineage if e["alert_field"] == "priority_score"]
    assert prio_rows and all(e["source_column"] == "spec.program.prioritization" for e in prio_rows)


def test_field_lineage_no_priority_when_disabled(tmp_path):
    import json

    run_dir = _run(tmp_path)  # stock spec, no prioritization block
    lineage = [
        json.loads(line)
        for line in (run_dir / "field_lineage.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert "priority_score" not in {e["alert_field"] for e in lineage}


def test_volume_falls_back_to_matched_row_ids_when_count_absent():
    """aggregation_window sum-only rules don't project `count`, but their
    alerts carry matched_row_ids — volume must reflect the txn count, not 0."""
    cfg = ProgramPrioritization(enabled=True)
    a_lo = score_alert({"sum_amount": 10000, "matched_row_ids": [1]}, _rule("high"), cfg)
    a_hi = score_alert(
        {"sum_amount": 10000, "matched_row_ids": list(range(20))}, _rule("high"), cfg
    )
    assert a_hi.score > a_lo.score  # more supporting txns -> higher volume -> higher score
    lo_vol = {c["feature"]: c["value"] for c in a_lo.explanation}["volume"]
    assert lo_vol > 0.0  # not zeroed out when count is absent but evidence exists


def test_scorer_rejects_non_finite_features():
    """NaN/inf sentinels parse as valid floats but must NOT yield a NaN/inf
    score — that would break the 0-1 contract and emit non-standard JSON."""
    import math as _m

    cfg = ProgramPrioritization(enabled=True)
    for bad in ("NaN", "inf", "-inf", float("nan"), float("inf")):
        res = score_alert({"sum_amount": bad, "count": bad}, _rule("high"), cfg)
        assert _m.isfinite(res.score) and 0.0 <= res.score <= 1.0, bad
        for c in res.explanation:
            assert _m.isfinite(c["contribution"])


def test_weights_reject_non_finite():
    """A YAML `.inf`/`.nan` weight must be rejected at validation time — left
    unchecked it would propagate into a NaN/Infinity priority_score and emit
    non-standard JSON in the regulator-facing report."""
    for bad in (float("inf"), float("-inf"), float("nan")):
        for field in ("severity", "risk_tier", "amount", "volume"):
            with pytest.raises(Exception):
                ProgramPrioritization(enabled=True, weights={field: bad})


def test_sum_amount_zero_not_dropped_to_amount():
    """A legitimate `sum_amount: 0` must be honoured by key presence, not fall
    through truthiness to a projected `amount` (which would inflate the feature)."""
    cfg = ProgramPrioritization(enabled=True)
    res = score_alert({"sum_amount": 0, "amount": 100000, "count": 1}, _rule("high"), cfg)
    amount_val = {c["feature"]: c["value"] for c in res.explanation}["amount"]
    assert amount_val == 0.0  # used sum_amount=0, did NOT borrow amount=100000


def test_negative_count_clamped_to_zero_volume():
    """A malformed negative `count` must clamp to 0 volume — never produce a
    negative normalised feature that subtracts from the score."""
    cfg = ProgramPrioritization(enabled=True)
    res = score_alert({"sum_amount": 1000, "count": -5}, _rule("high"), cfg)
    feats = {c["feature"]: c["value"] for c in res.explanation}
    assert feats["volume"] == 0.0
    assert all(0.0 <= c["value"] <= 1.0 for c in res.explanation if c["feature"] != "bias")
