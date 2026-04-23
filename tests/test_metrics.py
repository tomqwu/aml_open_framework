from datetime import datetime
from pathlib import Path

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.metrics import evaluate_metrics, render_report
from aml_framework.spec import load_spec

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def _run(tmp_path):
    spec = load_spec(EXAMPLE)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    result = run_spec(spec=spec, spec_path=EXAMPLE, data=data, as_of=as_of, artifacts_root=tmp_path)
    return spec, result


def test_metrics_are_computed_and_written(tmp_path):
    spec, result = _run(tmp_path)
    assert result.metrics, "expected metrics from the example spec"

    expected_ids = {m.id for m in spec.metrics}
    got_ids = {m.id for m in result.metrics}
    assert got_ids == expected_ids

    run_dir = Path(result.manifest["run_dir"])
    assert (run_dir / "metrics" / "metrics.json").exists()
    for report in spec.reports:
        assert (run_dir / "reports" / f"{report.id}.md").exists()


def test_alert_volume_metric_matches_alerts(tmp_path):
    _, result = _run(tmp_path)
    total_alerts = result.total_alerts
    vol = next(m for m in result.metrics if m.id == "alert_volume_total")
    assert vol.value == total_alerts


def test_ratio_metric_is_bounded(tmp_path):
    _, result = _run(tmp_path)
    ratio = next(m for m in result.metrics if m.id == "high_severity_alert_ratio")
    assert 0.0 <= ratio.value <= 1.0


def test_rag_band_is_assigned_when_thresholds_present(tmp_path):
    _, result = _run(tmp_path)
    vol = next(m for m in result.metrics if m.id == "alert_volume_total")
    assert vol.rag in {"green", "amber", "red"}


def test_report_markdown_includes_metric_name(tmp_path):
    spec, result = _run(tmp_path)
    exec_brief = next(r for r in spec.reports if r.id == "svp_exec_brief")
    md = render_report(spec, exec_brief, result.metrics)
    assert "SVP executive brief" in md
    assert "Overall status:" in md
    assert "High-severity alert share" in md


def test_typology_coverage_uses_rule_tags():
    spec = load_spec(EXAMPLE)
    # Pretend every tagged rule fired; coverage should be 1.0.
    alerts = {r.id: [{"customer_id": "C"}] for r in spec.rules if r.tags}
    results = evaluate_metrics(spec=spec, alerts=alerts, cases=[], decisions=[], data={})
    coverage = next(m for m in results if m.id == "typology_coverage")
    assert coverage.value == 1.0
    assert coverage.rag == "green"


def test_distinct_by_counts_unique_customers(tmp_path):
    _, result = _run(tmp_path)
    distinct = next(m for m in result.metrics if m.id == "distinct_customers_alerted")
    all_customer_ids = {a["customer_id"] for alist in result.alerts.values() for a in alist}
    assert distinct.value == len(all_customer_ids)
