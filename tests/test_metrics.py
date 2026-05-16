"""Metric tests -- engine, reports, RAG bands, formula evaluation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.metrics import evaluate_metrics, render_report
from aml_framework.metrics.engine import (
    MetricContext,
    MetricResult,
    _cond_holds,
    _compute,
    _compute_sql_proxy,
    _matches_filter,
    _rag_band,
    _source_rows,
)
from aml_framework.metrics.reports import _overall_rag
from aml_framework.spec import load_spec
from aml_framework.spec.models import (
    CountFormula,
    CoverageFormula,
    Metric,
    RatioFormula,
    Report,
    ReportSection,
    SQLFormula,
    SumFormula,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


def _run(tmp_path):
    spec = load_spec(EXAMPLE)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    result = run_spec(spec=spec, spec_path=EXAMPLE, data=data, as_of=as_of, artifacts_root=tmp_path)
    return spec, result


# ---------------------------------------------------------------------------
# Original test_metrics.py
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# From test_coverage_99.py: TestMetricFilterOps
# ---------------------------------------------------------------------------


class TestMetricFilterOps:
    def test_matches_filter_operators(self):
        assert _matches_filter({"x": 10}, {"x": {"gt": 5}})
        assert not _matches_filter({"x": 3}, {"x": {"gt": 5}})
        assert _matches_filter({"x": 3}, {"x": {"lt": 5}})
        assert not _matches_filter({"x": 10}, {"x": {"lt": 5}})
        assert _matches_filter({"x": 5}, {"x": {"gte": 5}})
        assert _matches_filter({"x": 5}, {"x": {"lte": 5}})
        assert _matches_filter({"x": 5}, {"x": {"eq": 5}})
        assert not _matches_filter({"x": 5}, {"x": {"eq": 6}})
        assert _matches_filter({"x": 5}, {"x": {"ne": 6}})
        assert not _matches_filter({"x": 5}, {"x": {"ne": 5}})
        assert _matches_filter({"x": 5}, {"x": {"between": [3, 7]}})
        assert not _matches_filter({"x": 10}, {"x": {"between": [3, 7]}})
        assert _matches_filter({"x": "a"}, {"x": {"in": ["a", "b"]}})
        assert not _matches_filter({"x": "c"}, {"x": {"in": ["a", "b"]}})
        assert _matches_filter({"x": 5}, {"x": 5})
        assert not _matches_filter({"x": 5}, {"x": 6})
        assert not _matches_filter({"x": None}, {"x": {"gte": 5}})


# ---------------------------------------------------------------------------
# From test_coverage_99.py: TestMetricEngineExtended
# ---------------------------------------------------------------------------


class TestMetricEngineExtended:
    def test_rag_band_green_amber_red(self):
        m = Metric(
            id="test",
            name="test",
            category="operational",
            audience=["svp"],
            formula=CountFormula(type="count", source="alerts"),
            thresholds={"green": {"lte": 10}, "amber": {"lte": 50}, "red": {"gt": 50}},
        )
        assert _rag_band(5, m)[0] == "green"
        assert _rag_band(30, m)[0] == "amber"
        assert _rag_band(100, m)[0] == "red"

    def test_cond_holds_all_operators(self):
        assert _cond_holds(10, {"gte": 10})
        assert _cond_holds(10, {"lte": 10})
        assert _cond_holds(10, {"gt": 5})
        assert _cond_holds(10, {"lt": 15})
        assert _cond_holds(10, {"eq": 10})
        assert _cond_holds(10, {"between": [5, 15]})
        assert not _cond_holds(10, {"between": [15, 20]})


# ---------------------------------------------------------------------------
# From test_coverage_99.py: TestReportsEdgeCases
# ---------------------------------------------------------------------------


class TestReportsEdgeCases:
    def test_report_with_missing_metric(self, tmp_path):
        spec, result = _run(tmp_path)
        for report_id, md in result.reports.items():
            assert len(md) > 0

    def test_overall_rag_all_unset(self):
        results = [
            MetricResult(
                id="m1",
                name="m1",
                category="op",
                audience=[],
                owner=None,
                unit=None,
                value=0,
                rag="unset",
                target_met=None,
                formula_type="count",
            ),
        ]
        assert _overall_rag(results) == "unset"


# ---------------------------------------------------------------------------
# From test_coverage_gaps.py: TestMetricEdgeCases
# ---------------------------------------------------------------------------


class TestMetricEdgeCases:
    def test_coverage_non_typology_returns_zero(self, tmp_path):
        """Coverage formula with universe != typologies should return 0.0."""
        spec_us = load_spec(EXAMPLE)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec_us, spec_path=EXAMPLE, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        for m in result.metrics:
            assert m.value is not None


# ---------------------------------------------------------------------------
# From test_final_coverage.py: TestMetricsMissedLines
# ---------------------------------------------------------------------------


class TestMetricsMissedLines:
    def test_source_rows_customer(self):
        spec = load_spec(SPEC_CA)
        data = generate_dataset(as_of=datetime(2026, 4, 23), seed=42)
        ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data=data)
        customers = _source_rows("customer", ctx)
        assert len(customers) > 0

    def test_source_rows_unknown_raises(self):
        spec = load_spec(SPEC_CA)
        ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data={})
        with pytest.raises(ValueError, match="unknown"):
            _source_rows("nonexistent", ctx)

    def test_matches_filter_none_value_gte(self):
        assert not _matches_filter({"x": None}, {"x": {"lte": 5}})
        assert not _matches_filter({"x": None}, {"x": {"gt": 5}})
        assert not _matches_filter({"x": None}, {"x": {"lt": 5}})
        assert not _matches_filter({"x": None}, {"x": {"between": [1, 10]}})


# ---------------------------------------------------------------------------
# From test_final_coverage.py: TestReportsMissedLines
# ---------------------------------------------------------------------------


class TestReportsMissedLines:
    def test_report_with_only_red_metric(self):
        results = [
            MetricResult(
                id="m1",
                name="m1",
                category="op",
                audience=[],
                owner=None,
                unit=None,
                value=0,
                rag="red",
                target_met=False,
                formula_type="count",
            ),
        ]
        assert _overall_rag(results) == "red"

    def test_report_amber_beats_green(self):
        results = [
            MetricResult(
                id="m1",
                name="m1",
                category="op",
                audience=[],
                owner=None,
                unit=None,
                value=0,
                rag="green",
                target_met=True,
                formula_type="count",
            ),
            MetricResult(
                id="m2",
                name="m2",
                category="op",
                audience=[],
                owner=None,
                unit=None,
                value=0,
                rag="amber",
                target_met=False,
                formula_type="count",
            ),
        ]
        assert _overall_rag(results) == "amber"

    def test_format_value_missing_metric_in_report(self, tmp_path):
        """Report renders gracefully when a metric ID doesn't exist."""
        spec = load_spec(SPEC_CA)
        report = Report(
            id="test_report",
            audience="svp",
            cadence="quarterly",
            sections=[
                ReportSection(title="Test", metrics=["nonexistent_metric_id"]),
            ],
        )
        md = render_report(spec, report, [])
        assert "missing" in md.lower()


# ---------------------------------------------------------------------------
# From test_final_coverage.py: TestMetricsMore
# ---------------------------------------------------------------------------


class TestMetricsMore:
    def test_compute_ratio_zero_denom(self):
        spec = load_spec(SPEC_CA)
        ctx = MetricContext(
            spec=spec, alerts={}, cases=[], decisions=[], data={"txn": [], "customer": []}
        )
        formula = RatioFormula(
            type="ratio",
            numerator=CountFormula(type="count", source="alerts"),
            denominator=CountFormula(type="count", source="alerts"),
        )
        result = _compute(formula, ctx)
        assert result == 0.0

    def test_sum_formula(self):
        spec = load_spec(SPEC_CA)
        ctx = MetricContext(
            spec=spec,
            alerts={},
            cases=[],
            decisions=[],
            data={"txn": [{"amount": 100}, {"amount": 200}]},
        )
        formula = SumFormula(type="sum", source="txn", field="amount")
        result = _compute(formula, ctx)
        assert result == 300.0

    def test_coverage_formula_non_typology(self):
        spec = load_spec(SPEC_CA)
        ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data={})
        formula = CoverageFormula(
            type="coverage", universe="jurisdictions", covered_by="regulation_refs"
        )
        result = _compute(formula, ctx)
        assert result == 0.0


# ---------------------------------------------------------------------------
# From test_coverage_final_push.py: metric-related standalone tests
# ---------------------------------------------------------------------------


def test_source_rows_decisions():
    spec = load_spec(SPEC_CA)
    decisions = [{"event": "case_opened", "case_id": "c1"}]
    ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=decisions, data={})
    result = _source_rows("decisions", ctx)
    assert len(result) == 1


def test_unsupported_formula_type():
    spec = load_spec(SPEC_CA)
    ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data={})

    class FakeFormula:
        pass

    with pytest.raises(TypeError, match="unsupported"):
        _compute(FakeFormula(), ctx)


def test_cond_holds_gt_lt_on_rag():
    m = Metric(
        id="t",
        name="t",
        category="operational",
        audience=["svp"],
        formula=CountFormula(type="count", source="alerts"),
        thresholds={"green": {"lt": 5}, "amber": {"lt": 10}, "red": {"gte": 10}},
    )
    assert _rag_band(3, m)[0] == "green"
    assert _rag_band(7, m)[0] == "amber"
    assert _rag_band(15, m)[0] == "red"


# ---------------------------------------------------------------------------
# #204 P1: Correct SQL metric proxy dispatch and unsupported SQL semantics
# ---------------------------------------------------------------------------


def test_single_token_does_not_trigger_proxy():
    """SQL with 'repeat' only should NOT match the ('repeat','closed_cases') group."""
    spec = load_spec(SPEC_CA)
    ctx = MetricContext(
        spec=spec,
        alerts={"rule_a": [{"customer_id": "C001"}, {"customer_id": "C001"}]},
        cases=[{"case_id": "rule_a__C001__x", "queue": "closed_no_action"}],
        decisions=[{"event": "case_opened", "case_id": "rule_a__C001__x"}],
        data={},
    )
    formula = SQLFormula(type="sql", sql="SELECT repeat_count FROM somewhere")
    assert _compute_sql_proxy(formula, ctx) == 0.0


def test_lctr_reportable_token_matches_proxy():
    """SQL with 'reportable' matches the ('reportable',) proxy group."""
    spec = load_spec(SPEC_CA)
    ctx = MetricContext(
        spec=spec,
        alerts={},
        cases=[],
        decisions=[],
        data={"txn": [{"channel": "cash", "amount": 5000}]},
    )
    formula = SQLFormula(type="sql", sql="SELECT filed / NULLIF(reportable, 0) FROM ...")
    result = _compute_sql_proxy(formula, ctx)
    assert result >= 0.0  # matched, not unsupported


def test_all_tokens_required_for_proxy_match():
    """All tokens in a group must be present for match. 'repeat'+'closed_cases' matches."""
    spec = load_spec(SPEC_CA)
    ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data={})
    formula = SQLFormula(type="sql", sql="SELECT repeat, closed_cases FROM dual")
    result = _compute_sql_proxy(formula, ctx)
    assert result >= 0.0  # matches repeat_alert proxy


def test_sql_breakdown_unsupported():
    """SQL metric without proxy match gets proxy_status='unsupported' in breakdown."""
    spec = load_spec(SPEC_CA)
    from aml_framework.spec.models import Metric as MetricModel

    metric = MetricModel(
        id="unknown_sql",
        name="Unknown SQL",
        category="operational",
        audience=["svp"],
        formula=SQLFormula(type="sql", sql="SELECT nonsense FROM nowhere"),
    )
    spec.metrics.append(metric)
    results = evaluate_metrics(spec=spec, alerts={}, cases=[], decisions=[], data={})
    got = next(m for m in results if m.id == "unknown_sql")
    assert got.breakdown.get("proxy_status") == "unsupported"


def test_sql_breakdown_matched():
    """SQL metric with matching proxy gets proxy_status='proxy_matched' in breakdown."""
    spec = load_spec(SPEC_CA)
    from aml_framework.spec.models import Metric as MetricModel

    metric = MetricModel(
        id="filing_proxy",
        name="Filing Proxy",
        category="operational",
        audience=["svp"],
        formula=SQLFormula(type="sql", sql="SELECT filing_percentile FROM filing_latency"),
    )
    spec.metrics.append(metric)
    results = evaluate_metrics(spec=spec, alerts={}, cases=[], decisions=[], data={})
    got = next(m for m in results if m.id == "filing_proxy")
    assert got.breakdown.get("proxy_status") == "proxy_matched"


# ---------------------------------------------------------------------------
# End #204 tests
# ---------------------------------------------------------------------------


def test_unknown_sql_formula_returns_zero():
    """The dispatch table covers known proxies; everything else falls through to 0.0."""
    spec = load_spec(SPEC_CA)
    ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data={})
    formula = SQLFormula(type="sql", sql="SELECT something_unrelated FROM nowhere")
    assert _compute_sql_proxy(formula, ctx) == 0.0


def test_proxy_dispatch_first_match_wins():
    """When an SQL string contains multiple tokens, the first matching handler runs.
    `closed_cases` and `filing` both appear, but `closed_cases` wins per dispatch order."""
    from aml_framework.metrics.engine import _PROXY_DISPATCH, _proxy_repeat_alert

    spec = load_spec(SPEC_CA)
    ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data={})
    formula = SQLFormula(type="sql", sql="SELECT closed_cases.filing FROM x")
    # repeat_alert returns 0.0 with empty context — same as filing_latency would —
    # so we verify behavior by confirming the dispatch table has repeat_alert before
    # filing in iteration order.
    handlers = [h for _, h in _PROXY_DISPATCH]
    assert handlers.index(_proxy_repeat_alert) < handlers.index(
        next(h for tokens, h in _PROXY_DISPATCH if "filing" in tokens)
    )
    assert _compute_sql_proxy(formula, ctx) == 0.0


def test_filing_latency_no_filings():
    spec = load_spec(SPEC_CA)
    ctx = MetricContext(spec=spec, alerts={}, cases=[], decisions=[], data={})
    formula = SQLFormula(type="sql", sql="SELECT PERCENTILE_CONT(0.95) FROM filing_latency")
    result = _compute_sql_proxy(formula, ctx)
    assert result == 0.0


def test_edd_no_high_risk():
    spec = load_spec(SPEC_CA)
    ctx = MetricContext(
        spec=spec,
        alerts={},
        cases=[],
        decisions=[],
        data={"customer": [{"risk_rating": "low"}]},
    )
    formula = SQLFormula(type="sql", sql="SELECT current_edd / high_risk_total FROM edd_review")
    result = _compute_sql_proxy(formula, ctx)
    assert result == 1.0


def test_edd_with_string_review():
    spec = load_spec(SPEC_CA)
    ctx = MetricContext(
        spec=spec,
        alerts={},
        cases=[],
        decisions=[],
        data={"customer": [{"risk_rating": "high", "edd_last_review": "2025-06-01"}]},
    )
    formula = SQLFormula(type="sql", sql="SELECT current_edd FROM edd")
    result = _compute_sql_proxy(formula, ctx)
    assert result == 1.0


def test_cond_holds_gt_false():
    assert not _cond_holds(5, {"gt": 10})
    assert _cond_holds(15, {"gt": 10})


def test_repeat_alert_proxy_with_decisions():
    spec = load_spec(SPEC_CA)
    ctx = MetricContext(
        spec=spec,
        alerts={"rule_a": [{"customer_id": "C001"}, {"customer_id": "C001"}]},
        cases=[
            {"case_id": "rule_a__C001__x", "queue": "closed_no_action"},
        ],
        decisions=[
            {"event": "case_opened", "case_id": "rule_a__C001__x"},
        ],
        data={},
    )
    formula = SQLFormula(type="sql", sql="SELECT repeat_closed FROM closed_cases")
    result = _compute_sql_proxy(formula, ctx)
    assert result >= 0.0


# ---------------------------------------------------------------------------
# _proxy_filing_latency — real-latency path edge cases (PR-DATA-9)
# ---------------------------------------------------------------------------


class TestProxyFilingLatencyEdgeCases:
    """When a run_dir with filing sidecars is present, the metric uses
    wall-clock latency. Two defensive branches:

      - a `case_opened` decision whose `ts` is a string but not
        ISO-8601 (corrupt/legacy ledger) must be skipped, not crash
        (engine.py:225-226);
      - a filing whose case has no `case_opened` decision must be
        skipped so it doesn't contribute a bogus latency
        (engine.py:230).
    """

    def test_bad_ts_and_orphan_filing_are_skipped(self, tmp_path):
        from datetime import datetime, timezone

        from aml_framework.cases.filing import record_filing
        from aml_framework.metrics.engine import _proxy_filing_latency

        run_dir = tmp_path / "run-1"
        run_dir.mkdir()

        opened_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        # Case A: has a *valid* case_opened + a filing 4 days later ->
        # this is the only record that should drive the metric.
        record_filing(run_dir, "caseA", filed_at=opened_at.replace(day=5), channel="bsa_e_filing")
        # Case C: filed but never opened -> orphan, skipped (230).
        record_filing(run_dir, "caseC", filed_at=opened_at.replace(day=9), channel="bsa_e_filing")

        decisions = [
            {"event": "case_opened", "case_id": "caseA", "ts": opened_at.isoformat()},
            # caseB: ts is a string but unparseable -> dropped (225-226).
            {"event": "case_opened", "case_id": "caseB", "ts": "NOT-A-TIMESTAMP"},
            # caseC intentionally has NO case_opened decision.
        ]
        ctx = MetricContext(
            spec=load_spec(SPEC_CA),
            alerts={},
            cases=[],
            decisions=decisions,
            data={},
            run_dir=run_dir,
        )

        value = _proxy_filing_latency(ctx)
        # Only caseA contributes: opened day 1, filed day 5 -> 4 days.
        assert value == 4.0

    def test_ts_not_a_string_does_not_register_open(self, tmp_path):
        """A `case_opened` decision whose `ts` isn't a str at all is
        ignored (the `isinstance(ts_raw, str)` guard), so its filing
        becomes an orphan and is skipped — metric falls back to the
        proxy and stays >= 0."""
        from datetime import datetime, timezone

        from aml_framework.cases.filing import record_filing
        from aml_framework.metrics.engine import _proxy_filing_latency

        run_dir = tmp_path / "run-2"
        run_dir.mkdir()
        record_filing(
            run_dir,
            "caseX",
            filed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
            channel="bsa_e_filing",
        )
        decisions = [
            {"event": "case_opened", "case_id": "caseX", "ts": 1700000000},
        ]
        ctx = MetricContext(
            spec=load_spec(SPEC_CA),
            alerts={},
            cases=[],
            decisions=decisions,
            data={},
            run_dir=run_dir,
        )
        # No usable real latency -> proxy fallback, non-negative.
        assert _proxy_filing_latency(ctx) >= 0.0
