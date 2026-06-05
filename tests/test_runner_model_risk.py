"""Runner integration for governed model-risk monitoring (#497).

Mirrors the priority_outcome / suppression_report posture: the artifact is
emitted + manifest-pinned ONLY when `program.model_risk_monitoring.enabled`,
and a run without the block is byte-identical (no file, no manifest key).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec
from aml_framework.spec.models import ModelRiskMonitoring

SPEC_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def _enable_mrm(spec):
    """Return a copy of `spec` with model_risk_monitoring enabled (specs are
    frozen, so we rebuild Program → AMLSpec via model_copy)."""
    prog = spec.program.model_copy(
        update={"model_risk_monitoring": ModelRiskMonitoring(enabled=True)}
    )
    return spec.model_copy(update={"program": prog})


def _run(spec, artifacts_root):
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    return run_spec(
        spec=spec, spec_path=SPEC_US, data=data, as_of=as_of, artifacts_root=artifacts_root
    )


def test_runner_emits_model_risk_report_when_enabled(tmp_path):
    spec = _enable_mrm(load_spec(SPEC_US))
    result = _run(spec, tmp_path)
    run_dir = Path(result.manifest["run_dir"])

    report_path = run_dir / "model_risk_report.json"
    assert report_path.exists(), "model_risk_report.json must be written when enabled"
    report = json.loads(report_path.read_text())
    assert report["enabled"] is True
    assert report["n_models"] >= 1

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert "model_risk_report_hash" in manifest
    assert manifest["model_risk_report_hash"]


def test_runner_no_model_risk_report_when_absent(tmp_path):
    spec = load_spec(SPEC_US)  # no model_risk_monitoring block
    assert spec.program.model_risk_monitoring is None
    result = _run(spec, tmp_path)
    run_dir = Path(result.manifest["run_dir"])

    assert not (run_dir / "model_risk_report.json").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert "model_risk_report_hash" not in manifest


def test_model_risk_report_deterministic_across_runs(tmp_path):
    spec = _enable_mrm(load_spec(SPEC_US))
    r1 = _run(spec, tmp_path / "a")
    r2 = _run(spec, tmp_path / "b")

    rd1 = Path(r1.manifest["run_dir"])
    rd2 = Path(r2.manifest["run_dir"])
    b1 = (rd1 / "model_risk_report.json").read_bytes()
    b2 = (rd2 / "model_risk_report.json").read_bytes()
    assert b1 == b2, "model_risk_report.json bytes must be deterministic across runs"

    m1 = json.loads((rd1 / "manifest.json").read_text())
    m2 = json.loads((rd2 / "manifest.json").read_text())
    assert m1["model_risk_report_hash"] == m2["model_risk_report_hash"]
