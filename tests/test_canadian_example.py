"""Tests for the Canadian Schedule I bank spec (TD Bank case study model)."""

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
    result = run_spec(spec=spec, spec_path=EXAMPLE, data=data, as_of=as_of, artifacts_root=tmp_path)
    return spec, result


def test_spec_validates():
    spec = load_spec(EXAMPLE)
    assert spec.program.jurisdiction == "CA"
    assert spec.program.regulator == "FINTRAC"
    assert len(spec.rules) == 10
    assert len(spec.workflow.queues) == 5


def test_pass_through_rule_fires(tmp_path):
    """Planted pass-through scenario (C0007) must trigger the rapid_pass_through rule."""
    _, result = _run(tmp_path)
    alerts = result.alerts.get("rapid_pass_through", [])
    assert len(alerts) >= 1, "planted pass-through case must be detected"
    assert any(a.get("customer_id") == "C0007" for a in alerts)


def test_shell_company_rule_fires(tmp_path):
    """Planted shell company (C0008, no business_activity) must trigger."""
    _, result = _run(tmp_path)
    alerts = result.alerts.get("shell_company_indicators", [])
    assert len(alerts) >= 1, "planted shell company must be detected"
    assert any(a.get("customer_id") == "C0008" for a in alerts)


def test_channel_coverage_metric(tmp_path):
    """Coverage metric must be computed. When all typology tags fire, it should be 1.0."""
    _, result = _run(tmp_path)
    coverage = [m for m in result.metrics if m.id == "channel_coverage_gap"]
    assert len(coverage) == 1
    # With all rules firing, typology coverage should be 1.0 (GREEN).
    assert coverage[0].value == 1.0
    assert coverage[0].rag == "green"


def test_internal_alert_ignored_metric_exists(tmp_path):
    """The repeat-alert metric must be computed (even as 0.0 in reference engine)."""
    _, result = _run(tmp_path)
    ignored = [m for m in result.metrics if m.id == "internal_alert_ignored"]
    assert len(ignored) == 1
    assert ignored[0].rag == "green"  # 0.0 is within green threshold


def test_all_five_reports_generated(tmp_path):
    """All 5 audience reports must be rendered."""
    _, result = _run(tmp_path)
    expected = {"cao_quarterly", "mlro_monthly", "fintrac_readiness", "ops_daily", "osfi_exam_prep"}
    assert set(result.reports.keys()) == expected


def test_run_is_reproducible(tmp_path):
    """Two identical runs must produce the same output hashes."""
    spec = load_spec(EXAMPLE)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)

    r1 = run_spec(
        spec=spec, spec_path=EXAMPLE, data=data, as_of=as_of, artifacts_root=tmp_path / "a"
    )
    r2 = run_spec(
        spec=spec, spec_path=EXAMPLE, data=data, as_of=as_of, artifacts_root=tmp_path / "b"
    )

    for rule_id, hash1 in r1.manifest["rule_outputs"].items():
        assert hash1 == r2.manifest["rule_outputs"][rule_id], f"output hash drift on rule {rule_id}"
