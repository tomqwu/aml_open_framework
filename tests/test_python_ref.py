"""Tests for python_ref rule execution pipeline."""

from datetime import datetime
from pathlib import Path

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


def _run(tmp_path):
    spec = load_spec(EXAMPLE)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    return spec, run_spec(
        spec=spec, spec_path=EXAMPLE, data=data, as_of=as_of, artifacts_root=tmp_path
    )


def test_python_ref_rule_executes(tmp_path):
    """The ml_risk_scorer python_ref rule must execute and produce alerts."""
    _, result = _run(tmp_path)
    alerts = result.alerts.get("ml_risk_scorer", [])
    assert len(alerts) >= 1, "heuristic scorer should flag at least one customer"


def test_python_ref_alerts_have_risk_score(tmp_path):
    """Each alert from the scorer must include a risk_score field."""
    _, result = _run(tmp_path)
    for alert in result.alerts.get("ml_risk_scorer", []):
        assert "risk_score" in alert, "scorer must return risk_score"
        assert alert["risk_score"] >= 0.65, "score must be above threshold"


def test_python_ref_creates_cases(tmp_path):
    """python_ref alerts must generate case files like any other rule."""
    _, result = _run(tmp_path)
    run_dir = Path(result.manifest["run_dir"])
    ml_cases = list((run_dir / "cases").glob("ml_risk_scorer__*"))
    assert len(ml_cases) >= 1, "scorer alerts must create case files"


def test_python_ref_audit_trail(tmp_path):
    """python_ref execution must be recorded in the audit ledger."""
    _, result = _run(tmp_path)
    run_dir = Path(result.manifest["run_dir"])
    sql_file = run_dir / "rules" / "ml_risk_scorer.sql"
    assert sql_file.exists(), "audit trail must record python_ref stub"
    content = sql_file.read_text()
    assert "python_ref" in content
    assert "heuristic_risk_v1" in content
