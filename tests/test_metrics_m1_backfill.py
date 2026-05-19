"""Source guards for PR-M1-metrics (the metrics "backfill" slice).

Four example specs shipped rules but no `metrics:` block. This PR
pastes a curated set of core metrics (drawn from the new
`spec/library/core_metrics.yaml` snippet) into each, tuned with that
spec's real high/critical-severity rule ids.

These are fast `[dev]`-safe guards (no streamlit, no Playwright): they
pin that (a) the curated library file exists and is referenced from
the library package docstring, (b) each of the four specs now carries
the expected core metrics, and (c) every metric evaluates to a real
value/rag at seed 42 — so a wrong rule id (which silently computes 0)
or a dropped metric block can't regress unnoticed.

`high_severity_alert_ratio` is only carried by specs whose rule set has
a mix of severities (here: us_rtp_fednow, which excludes its one
`medium` rule from the numerator). For an all-high-severity spec the
share is a constant 100% — a structurally always-green risk metric that
misstates program risk — so it is intentionally omitted there, and
these guards pin that contract both ways.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.metrics.engine import evaluate_metrics
from aml_framework.spec import load_spec

REPO = Path(__file__).resolve().parents[1]
LIBRARY = REPO / "src/aml_framework/spec/library"
CORE_METRICS = LIBRARY / "core_metrics.yaml"

# The four zero-metric specs this PR backfills, and the core metric ids
# every one of them must now carry.
BACKFILLED = ("us_rtp_fednow", "uk_app_fraud", "trade_based_ml", "cyber_enabled_fraud")
CORE_METRIC_IDS = {
    "alert_volume_total",
    "typology_coverage",
    "cases_opened",
}
# high_severity_alert_ratio is meaningful ONLY where the rule set mixes
# severities so the share is a real fraction with reachable bands. The
# all-high-severity specs omit it (constant-100% = always-green noise).
HIGH_SEV_RATIO_SPECS = ("us_rtp_fednow",)


def test_core_metrics_library_file_exists():
    assert CORE_METRICS.exists(), f"core_metrics.yaml missing at {CORE_METRICS}"
    text = CORE_METRICS.read_text(encoding="utf-8")
    # It documents the copy-paste contract (NOT auto-include) and uses
    # only the existing formula union.
    assert "copy-pasteable" in text or "copy-paste" in text
    assert "NOT an auto-include" in text
    for fid in ("alert_volume_total", "high_severity_alert_ratio", "typology_coverage"):
        assert fid in text


def test_core_metrics_referenced_in_library_docstring():
    import aml_framework.spec.library as lib

    assert lib.__doc__ is not None
    assert "core_metrics.yaml" in lib.__doc__


@pytest.mark.parametrize("name", BACKFILLED)
def test_spec_now_has_core_metrics(name):
    spec = load_spec(REPO / "examples" / name / "aml.yaml")
    ids = {m.id for m in spec.metrics}
    assert len(spec.metrics) >= 3, f"{name} should have >=3 metrics, got {len(spec.metrics)}"
    assert CORE_METRIC_IDS <= ids, f"{name} missing core metrics: {CORE_METRIC_IDS - ids}"
    if name in HIGH_SEV_RATIO_SPECS:
        assert "high_severity_alert_ratio" in ids, f"{name} should carry the severity-share metric"
    else:
        assert "high_severity_alert_ratio" not in ids, (
            f"{name} is all-high-severity — the constant-100% ratio must be omitted, "
            "not shipped as a structurally always-green risk metric"
        )
    # A report must reference the metrics (loader cross-validates this).
    assert spec.reports, f"{name} should ship at least one report"


@pytest.mark.parametrize("name", HIGH_SEV_RATIO_SPECS)
def test_spec_high_severity_filter_targets_real_rules(name):
    """Where high_severity_alert_ratio is carried, its numerator filter
    must list rule ids that exist — a wrong id silently computes 0 — and
    must be a proper subset (else the share is a degenerate constant)."""
    spec = load_spec(REPO / "examples" / name / "aml.yaml")
    rule_ids = {r.id for r in spec.rules}
    metric = next(m for m in spec.metrics if m.id == "high_severity_alert_ratio")
    listed = metric.formula.numerator.filter["rule_id"]["in"]
    assert listed, f"{name} high_severity_alert_ratio has an empty rule_id filter"
    for rid in listed:
        assert rid in rule_ids, f"{name}: high-severity filter references unknown rule '{rid}'"
    assert set(listed) < rule_ids, (
        f"{name}: numerator lists every rule — share is a constant, "
        "use a real high/critical subset or omit the metric"
    )


@pytest.mark.parametrize("name", BACKFILLED)
def test_backfilled_metrics_evaluate_cleanly(name):
    """Every new metric must produce a value + rag at seed 42 — not crash
    and not silently fall to 0 from a typo'd rule id."""
    p = REPO / "examples" / name / "aml.yaml"
    spec = load_spec(p)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    with tempfile.TemporaryDirectory() as d:
        result = run_spec(spec=spec, spec_path=p, data=data, as_of=as_of, artifacts_root=Path(d))
        run_dir = Path(result.manifest["run_dir"])
        cases = [json.loads(f.read_bytes()) for f in sorted((run_dir / "cases").glob("*.json"))]
        decisions = []
        decisions_path = run_dir / "decisions.jsonl"
        if decisions_path.exists():
            for line in decisions_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    decisions.append(json.loads(line))
        results = evaluate_metrics(
            spec=spec,
            alerts=result.alerts,
            cases=cases,
            decisions=decisions,
            data=data,
            run_dir=run_dir,
        )

    assert {m.id for m in results} == {m.id for m in spec.metrics}
    by_id = {m.id: m for m in results}
    for mid in CORE_METRIC_IDS:
        m = by_id[mid]
        assert isinstance(m.value, (int, float))
        assert m.rag in {"green", "amber", "red", "unset"}

    # alert_volume_total and cases_opened are non-zero on the seeded
    # dataset (these specs all fire on planted positives), proving the
    # `count` sources resolve.
    assert by_id["alert_volume_total"].value >= 1
    assert by_id["cases_opened"].value >= 1
    if name in HIGH_SEV_RATIO_SPECS:
        # A real bounded fraction (>0 because the high/critical rules
        # fire on the plants). Band reachability is pinned structurally
        # by test_spec_high_severity_filter_targets_real_rules' subset
        # check — the runtime value may legitimately be 1.0 if the
        # excluded lower-severity rule happens not to fire at seed 42.
        hs = by_id["high_severity_alert_ratio"]
        assert isinstance(hs.value, (int, float))
        assert hs.rag in {"green", "amber", "red", "unset"}
        assert 0.0 < hs.value <= 1.0
